"""Admin dashboard returns the exact AdminStats shape the frontend reads."""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Payment
from app.models.catalog import AiModel
from tests.conftest import admin_headers


def test_dashboard_shape(app, client, admin, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        db.session.add(AiModel(slug="m1", display_name="M1", capability="text",
                               provider_key="openai_compat", provider_model_name="x", pricing_type="token",
                               is_active=True))
        db.session.add(Payment(user_id=uid, gateway="zibal", amount_irr=500_000,
                               status="paid", idempotency_key="pay-today"))
        old = Payment(user_id=uid, gateway="zibal", amount_irr=200_000, status="paid",
                       idempotency_key="pay-old")
        db.session.add(old)
        db.session.flush()
        old.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
        db.session.commit()
    r = client.get("/api/v1/admin/dashboard", headers=admin_headers(client, admin))
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert set(data.keys()) == {
        "total_users", "active_users", "total_revenue_irr", "revenue_today_irr",
        "payments_today", "jobs_today", "active_models", "pending_gallery_items",
    }
    assert data["total_users"] == 1
    assert data["active_users"] == 1
    assert data["total_revenue_irr"] == 700_000
    assert data["revenue_today_irr"] == 500_000
    assert data["payments_today"] == 1
    assert data["active_models"] == 1
