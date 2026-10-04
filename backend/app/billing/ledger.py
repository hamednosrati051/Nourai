"""Transaction-safe wallet ledger.

Every balance change goes through :func:`post_transaction`:

- the wallet row is locked with ``SELECT ... FOR UPDATE`` inside the caller's
  transaction,
- a ledger row is inserted with ``balance_after_irr``,
- the wallet balance/version is updated in the same transaction,
- ``idempotency_key`` is unique, so retries never double-post,
- balances can never go negative.

Callers must wrap usage in a transaction (``db.session`` / ``session.begin()``)
and commit once at the end.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.models.wallet import (
    TX_ADMIN_ADJUSTMENT,
    TX_BONUS,
    TX_DEPOSIT,
    TX_PLAN_PURCHASE,
    TX_REFUND,
    TX_RELEASE,
    TX_RESERVE,
    TX_SETTLEMENT,
    WalletAccount,
    WalletTransaction,
)


class LedgerError(Exception):
    pass


class InsufficientBalance(LedgerError):
    pass


class DuplicateIdempotencyKey(LedgerError):
    def __init__(self, idempotency_key: str):
        super().__init__(f"duplicate idempotency key: {idempotency_key}")
        self.idempotency_key = idempotency_key


def get_wallet_for_update(session, user_id: str) -> WalletAccount:
    """Fetch (or create) the user's wallet, locking the row for update."""
    wallet = (
        session.query(WalletAccount)
        .filter_by(user_id=user_id)
        .with_for_update()
        .one_or_none()
    )
    if wallet is None:
        wallet = WalletAccount(user_id=user_id, currency="IRR", balance_irr=0, version=0)
        session.add(wallet)
        session.flush()
        wallet = (
            session.query(WalletAccount)
            .filter_by(user_id=user_id)
            .with_for_update()
            .one()
        )
    return wallet


def post_transaction(
    session,
    *,
    wallet: WalletAccount,
    type: str,
    amount_irr: int,
    reference_type: str | None = None,
    reference_id: str | None = None,
    idempotency_key: str,
    description: str | None = None,
    created_by_admin_id: str | None = None,
) -> WalletTransaction:
    """Post one ledger entry and move the balance atomically."""
    if not isinstance(amount_irr, int):
        raise TypeError("amount_irr must be an integer (IRR)")
    if not idempotency_key:
        raise ValueError("idempotency_key is required")

    balance_after = wallet.balance_irr + amount_irr
    if balance_after < 0:
        raise InsufficientBalance(
            f"insufficient balance: {wallet.balance_irr} + ({amount_irr})"
        )

    tx = WalletTransaction(
        wallet_id=wallet.id,
        type=type,
        amount_irr=amount_irr,
        balance_after_irr=balance_after,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
        created_by_admin_id=created_by_admin_id,
    )
    session.add(tx)
    wallet.balance_irr = balance_after
    wallet.version = (wallet.version or 0) + 1
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateIdempotencyKey(idempotency_key) from exc
    return tx


# -- convenience operations -------------------------------------------------
def deposit(session, *, wallet, amount_irr: int, idempotency_key: str,
            reference_type: str | None = None, reference_id: str | None = None,
            description: str | None = None) -> WalletTransaction:
    if amount_irr <= 0:
        raise ValueError("deposit amount must be positive")
    return post_transaction(
        session, wallet=wallet, type=TX_DEPOSIT, amount_irr=amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def reserve(session, *, wallet, amount_irr: int, idempotency_key: str,
            reference_type: str | None = None, reference_id: str | None = None,
            description: str | None = None) -> WalletTransaction:
    """Hold an estimated amount. Raises InsufficientBalance when too low."""
    if amount_irr <= 0:
        raise ValueError("reserve amount must be positive")
    return post_transaction(
        session, wallet=wallet, type=TX_RESERVE, amount_irr=-amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def settle(session, *, wallet, reserved_amount_irr: int, final_amount_irr: int,
           idempotency_key: str, reference_type: str | None = None,
           reference_id: str | None = None,
           description: str | None = None) -> WalletTransaction:
    """Convert a reserve into the final charge.

    Posts a single adjusting entry: ``reserved - final``. Positive when the
    final cost is lower (releases the difference), negative when higher.
    The balance can never go negative, even if the final cost exceeds the
    estimate.
    """
    if reserved_amount_irr < 0 or final_amount_irr < 0:
        raise ValueError("amounts must be non-negative")
    adjustment = reserved_amount_irr - final_amount_irr
    return post_transaction(
        session, wallet=wallet, type=TX_SETTLEMENT, amount_irr=adjustment,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def release(session, *, wallet, reserved_amount_irr: int, idempotency_key: str,
            reference_type: str | None = None, reference_id: str | None = None,
            description: str | None = None) -> WalletTransaction:
    """Free a held amount after a failed request (no charge)."""
    if reserved_amount_irr <= 0:
        raise ValueError("release amount must be positive")
    return post_transaction(
        session, wallet=wallet, type=TX_RELEASE, amount_irr=reserved_amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def refund(session, *, wallet, amount_irr: int, idempotency_key: str,
           reference_type: str | None = None, reference_id: str | None = None,
           description: str | None = None) -> WalletTransaction:
    if amount_irr <= 0:
        raise ValueError("refund amount must be positive")
    return post_transaction(
        session, wallet=wallet, type=TX_REFUND, amount_irr=amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def bonus(session, *, wallet, amount_irr: int, idempotency_key: str,
          reference_type: str | None = None, reference_id: str | None = None,
          description: str | None = None) -> WalletTransaction:
    """Promotional credit attached to a top-up plan purchase.

    Kept as a separate transparent ledger entry (type "bonus") rather than
    folding it into the deposit, so the paid amount and the bonus are each
    auditable on their own.
    """
    if amount_irr <= 0:
        raise ValueError("bonus amount must be positive")
    return post_transaction(
        session, wallet=wallet, type=TX_BONUS, amount_irr=amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def plan_purchase(session, *, wallet, amount_irr: int, idempotency_key: str,
                  reference_type: str | None = None, reference_id: str | None = None,
                  description: str | None = None) -> WalletTransaction:
    """Buy a subscription with wallet credit (deducts the plan price).

    Raises InsufficientBalance when the wallet cannot cover the price.
    """
    if amount_irr <= 0:
        raise ValueError("plan price must be positive")
    return post_transaction(
        session, wallet=wallet, type=TX_PLAN_PURCHASE, amount_irr=-amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
    )


def admin_adjust(session, *, wallet, amount_irr: int, idempotency_key: str,
                 admin_id: str, reference_type: str | None = None,
                 reference_id: str | None = None,
                 description: str | None = None) -> WalletTransaction:
    """Admin balance change (signed amount) with an audit trail."""
    if amount_irr == 0:
        raise ValueError("adjustment amount must be non-zero")
    return post_transaction(
        session, wallet=wallet, type=TX_ADMIN_ADJUSTMENT, amount_irr=amount_irr,
        reference_type=reference_type, reference_id=reference_id,
        idempotency_key=idempotency_key, description=description,
        created_by_admin_id=admin_id,
    )
