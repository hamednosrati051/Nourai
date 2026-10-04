"""Wallet account + immutable ledger transactions.

The ledger is the source of truth for balances: the balance column is only
ever changed together with a ledger row inside one transaction, and balances
are never overwritten directly.
"""
from __future__ import annotations

from sqlalchemy import CHAR, BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

TX_DEPOSIT = "deposit"
TX_BONUS = "bonus"  # promotional credit attached to a top-up plan purchase
TX_RESERVE = "reserve"
TX_SETTLEMENT = "settlement"
TX_RELEASE = "release"
TX_REFUND = "refund"
TX_ADMIN_ADJUSTMENT = "admin_adjustment"
TX_PLAN_PURCHASE = "plan_purchase"  # subscription bought with wallet credit

TRANSACTION_TYPES = (
    TX_DEPOSIT,
    TX_BONUS,
    TX_RESERVE,
    TX_SETTLEMENT,
    TX_RELEASE,
    TX_REFUND,
    TX_ADMIN_ADJUSTMENT,
    TX_PLAN_PURCHASE,
)


class WalletAccount(Base):
    __tablename__ = "wallet_accounts"

    user_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), default="IRR", nullable=False)
    # Canonical unit: integer IRR. Never negative.
    balance_irr: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # Optimistic-locking version, bumped on every balance change.
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    wallet_id: Mapped[str] = mapped_column(
        CHAR(36), ForeignKey("wallet_accounts.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Signed integer IRR: deposits/adjustments positive, charges negative.
    amount_irr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_irr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_admin_id: Mapped[str | None] = mapped_column(
        CHAR(36), ForeignKey("admin_users.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_wallet_tx_wallet_created", "wallet_id", "created_at"),
        Index("ix_wallet_tx_reference", "reference_type", "reference_id"),
    )
