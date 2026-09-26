"""Wallet endpoints: balance and immutable transaction history."""
from __future__ import annotations

from flask import Blueprint, g

from app.api.deps import login_required, paginate_query, pagination_params, success_response
from app.billing.currency import irr_to_toman
from app.billing.ledger import get_wallet_for_update
from app.extensions import db
from app.models import WalletTransaction

bp = Blueprint("wallet", __name__)


@bp.get("/wallet")
@login_required
def get_wallet():
    wallet = get_wallet_for_update(db.session, g.current_user_id)
    db.session.commit()
    return success_response({
        "currency": wallet.currency,
        "balance_irr": wallet.balance_irr,
        "balance_toman": irr_to_toman(wallet.balance_irr),
    })


@bp.get("/wallet/transactions")
@login_required
def list_transactions():
    wallet = get_wallet_for_update(db.session, g.current_user_id)
    db.session.commit()
    page, page_size = pagination_params()
    query = (
        db.session.query(WalletTransaction)
        .filter_by(wallet_id=wallet.id)
        .order_by(WalletTransaction.created_at.desc())
    )
    items, meta = paginate_query(query, page, page_size)
    return success_response(
        [
            {
                "id": tx.id,
                "type": tx.type,
                "amount_irr": tx.amount_irr,
                "balance_after_irr": tx.balance_after_irr,
                "reference_type": tx.reference_type,
                "description": tx.description,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in items
        ],
        meta,
    )
