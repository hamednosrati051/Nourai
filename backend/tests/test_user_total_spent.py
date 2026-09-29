"""total_spent_irr in the admin user summary."""
from app.extensions import db
from app.models import User
from app.models.wallet import WalletAccount, WalletTransaction
from app.services.users import user_summary
from tests.conftest import admin_headers


def _tx(wallet_id, amount_irr, key):
    db.session.add(WalletTransaction(
        wallet_id=wallet_id, type="test", amount_irr=amount_irr,
        balance_after_irr=0, idempotency_key=key,
    ))


def test_user_summary_includes_total_spent(app, client, admin, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        wallet = WalletAccount(user_id=uid, balance_irr=700_000)
        db.session.add(wallet)
        db.session.flush()
        _tx(wallet.id, 1_000_000, "dep-1")    # deposit: not spent
        _tx(wallet.id, -200_000, "chg-1")     # charges: spent
        _tx(wallet.id, -100_000, "chg-2")
        _tx(wallet.id, 50_000, "adj-1")       # positive adjustment: not spent
        db.session.commit()
        summary = user_summary(db.session, db.session.get(User, uid))
    assert summary["total_spent_irr"] == 300_000
    assert summary["balance_irr"] == 700_000


def test_user_summary_total_spent_zero_without_wallet(app, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        summary = user_summary(db.session, db.session.get(User, uid))
    assert summary["total_spent_irr"] == 0


def test_admin_user_detail_returns_total_spent(app, client, admin, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        wallet = WalletAccount(user_id=uid, balance_irr=0)
        db.session.add(wallet)
        db.session.flush()
        _tx(wallet.id, -500_000, "chg-9")
        db.session.commit()
    r = client.get(f"/api/v1/admin/users/{uid}", headers=admin_headers(client, admin))
    assert r.status_code == 200
    assert r.get_json()["data"]["total_spent_irr"] == 500_000
