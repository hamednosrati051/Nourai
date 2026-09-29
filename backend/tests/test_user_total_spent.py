"""total_spent_irr in the admin user summary comes from usage charges."""
from app.extensions import db
from app.models import UsageEvent, User
from app.models.wallet import WalletAccount
from app.services.users import user_summary


def _usage(user_id, charged, status="succeeded"):
    db.session.add(UsageEvent(user_id=user_id, status=status,
                              charged_amount_irr=charged))


def test_user_summary_includes_total_spent(app, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        db.session.add(WalletAccount(user_id=uid, balance_irr=700_000))
        _usage(uid, 200_000)              # chat/image/audio charges
        _usage(uid, 100_000)
        _usage(uid, 0, status="failed")   # failed request: not spent
        db.session.commit()
        summary = user_summary(db.session, db.session.get(User, uid))
    assert summary["total_spent_irr"] == 300_000
    assert summary["balance_irr"] == 700_000


def test_user_summary_total_spent_zero_without_usage(app, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        summary = user_summary(db.session, db.session.get(User, uid))
    assert summary["total_spent_irr"] == 0


def test_admin_user_detail_returns_total_spent(app, client, admin, user):
    from tests.conftest import admin_headers
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        _usage(uid, 500_000)
        db.session.commit()
    r = client.get(f"/api/v1/admin/users/{uid}", headers=admin_headers(client, admin))
    assert r.status_code == 200
    assert r.get_json()["data"]["total_spent_irr"] == 500_000
