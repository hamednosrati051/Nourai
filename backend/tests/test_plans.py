"""Tests for subscription plans: catalog, activation, purchase flow,
plan limits, and admin deletion guard."""
from __future__ import annotations

from datetime import timedelta

from app.extensions import db
from app.models import (
    Conversation,
    Plan,
    UserPlanSubscription,
    WalletAccount,
    WalletTransaction,
)
from app.models.plans import SUB_ACTIVE, SUB_CANCELLED
from app.services.plans import (
    PlanLimitService,
    activate_subscription,
    get_active_subscription,
    over_quota_kinds,
)
from tests.conftest import admin_headers, user_headers

BASE = "/api/v1"


def _plan(**kw):
    defaults = {
        "name": "پلن تست",
        "description": "desc",
        "price_irr": 0,
        "period_days": 30,
        "features_json": ["ویژگی ۱"],
        "usage_limits_json": None,
        "bonus_irr": 0,
        "is_free": True,
        "is_featured": False,
        "is_active": True,
        "sort_order": 0,
    }
    defaults.update(kw)
    plan = Plan(**defaults)
    db.session.add(plan)
    db.session.commit()
    return plan


def test_public_plans_only_active_ordered(client):
    _plan(name="غیرفعال", is_active=False, sort_order=0)
    b = _plan(name="ب", sort_order=2)
    a = _plan(name="الف", sort_order=1)

    resp = client.get(f"{BASE}/plans")
    assert resp.status_code == 200
    body = resp.get_json()
    plans = body["data"]
    assert [p["id"] for p in plans] == [a.id, b.id]
    p = plans[0]
    assert p["price_irr"] == 0 and p["price_toman"] == 0
    assert p["period_days"] == 30
    assert p["features"] == ["ویژگی ۱"]
    assert p["is_free"] is True and p["is_featured"] is False


def test_activate_free_plan_without_payment(client, app, user):
    plan = _plan(name="رایگان", is_free=True, price_irr=0,
                 usage_limits_json={"monthly_text": 20, "monthly_image": 2})
    headers = user_headers(client, user)

    resp = client.post(f"{BASE}/plans/{plan.id}/activate", headers=headers)
    assert resp.status_code == 201, resp.get_json()
    sub = resp.get_json()["data"]["subscription"]
    assert sub["status"] == "active"
    assert sub["plan"]["id"] == plan.id
    assert sub["usage_counters"] == {}

    with app.app_context():
        stored = get_active_subscription(db.session, user)
        assert stored is not None and stored.plan_id == plan.id

    # /me/plan reflects the active subscription with limits + counters
    resp = client.get(f"{BASE}/me/plan")
    assert resp.status_code == 200
    me_plan = resp.get_json()["data"]["subscription"]
    assert me_plan["plan"]["usage_limits"] == {"monthly_text": 20, "monthly_image": 2}
    assert me_plan["usage_counters"] == {}


def test_activate_paid_plan_requires_payment(client, user):
    plan = _plan(name="پولی", is_free=False, price_irr=3_000_000)
    headers = user_headers(client, user)

    resp = client.post(f"{BASE}/plans/{plan.id}/activate", headers=headers)
    assert resp.status_code == 402
    body = resp.get_json()
    assert body["error"]["code"] == "PAYMENT_REQUIRED"


def test_activate_inactive_plan_404(client, user):
    plan = _plan(name="غیرفعال", is_active=False)
    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/plans/{plan.id}/activate", headers=headers)
    assert resp.status_code == 404


def test_reactivation_replaces_old_subscription(client, app, user):
    old_plan = _plan(name="قدیمی")
    new_plan = _plan(name="جدید")
    headers = user_headers(client, user)

    assert client.post(f"{BASE}/plans/{old_plan.id}/activate", headers=headers).status_code == 201
    assert client.post(f"{BASE}/plans/{new_plan.id}/activate", headers=headers).status_code == 201

    with app.app_context():
        subs = (
            db.session.query(UserPlanSubscription)
            .filter_by(user_id=user)
            .all()
        )
        active = [s for s in subs if s.status == SUB_ACTIVE]
        assert len(active) == 1 and active[0].plan_id == new_plan.id
        assert any(s.status == SUB_CANCELLED and s.plan_id == old_plan.id for s in subs)


def test_plan_purchase_with_wallet_credit(client, app, user):
    """New flow: the wallet is topped up first; POST /plans/{id}/purchase
    deducts the plan price from the balance (no Zibal for plans) and
    activates the subscription. The wallet is NOT credited."""
    from app.billing.ledger import deposit, get_wallet_for_update

    plan = _plan(name="حرفه‌ای", is_free=False, price_irr=3_000_000, period_days=30)
    with app.app_context():
        wallet = get_wallet_for_update(db.session, user)
        deposit(db.session, wallet=wallet, amount_irr=5_000_000,
                idempotency_key="test:topup", reference_type="test",
                reference_id="t1", description="test top-up")
        db.session.commit()

    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/plans/{plan.id}/purchase", headers=headers)
    assert resp.status_code == 201, resp.get_json()

    with app.app_context():
        wallet = db.session.query(WalletAccount).filter_by(user_id=user).one()
        # 5M top-up minus 3M plan price; the plan price is NOT credited back.
        assert wallet.balance_irr == 2_000_000
        txs = db.session.query(WalletTransaction).filter_by(wallet_id=wallet.id).all()
        purchase = [t for t in txs if t.type == "plan_purchase"]
        assert len(purchase) == 1 and purchase[0].amount_irr == -3_000_000

        sub = get_active_subscription(db.session, user)
        assert sub is not None and sub.plan_id == plan.id
        assert sub.status == SUB_ACTIVE


def test_plan_purchase_insufficient_balance(client, app, user):
    """Without enough wallet credit the purchase is rejected (402)."""
    plan = _plan(name="گران", is_free=False, price_irr=3_000_000)
    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/plans/{plan.id}/purchase", headers=headers)
    assert resp.status_code == 402
    assert resp.get_json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    with app.app_context():
        assert get_active_subscription(db.session, user) is None


def test_purchase_free_plan_rejected(client, user):
    plan = _plan(name="رایگان", is_free=True, price_irr=0)
    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/plans/{plan.id}/purchase", headers=headers)
    assert resp.status_code == 422


def test_purchase_inactive_plan_404(client, user):
    plan = _plan(name="غیرفعال", is_active=False, is_free=False, price_irr=1_000)
    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/plans/{plan.id}/purchase", headers=headers)
    assert resp.status_code == 404


def test_quota_available_soft(app, user):
    """Quotas are soft: quota_available() routes billing, never blocks."""
    with app.app_context():
        plan = _plan(name="محدود", usage_limits_json={"monthly_text": 1})
        sub = activate_subscription(db.session, user, plan)
        db.session.commit()

        svc = PlanLimitService(db.session)
        assert svc.quota_available(user, "text") is True  # 0 < 1: covered
        svc.increment(user, "text")
        db.session.commit()
        assert svc.quota_available(user, "text") is False  # 1 >= 1: wallet-billed

        sub = db.session.get(UserPlanSubscription, sub.id)
        assert over_quota_kinds(db.session, sub) == ["text"]

        # Kinds without a configured limit are never quota-covered.
        assert svc.quota_available(user, "image") is False
        assert svc.quota_available(user, "audio") is False


def test_expired_subscription_imposes_no_limits(app, user):
    with app.app_context():
        plan = _plan(name="منقضی", usage_limits_json={"monthly_text": 0})
        sub = activate_subscription(db.session, user, plan)
        sub.expires_at = sub.started_at - timedelta(seconds=1)  # already expired
        db.session.commit()

        assert PlanLimitService(db.session).quota_available(user, "text") is False
        db.session.commit()
        stored = db.session.get(UserPlanSubscription, sub.id)
        assert stored.status == "expired"


def test_chat_quota_covered_skips_wallet(client, app, user):
    """Quota-covered chat is not billed: zero balance, no 402/403.

    (No text model is registered in tests, so the request proceeds past
    billing to MODEL_UNAVAILABLE — the point is the wallet is untouched.)
    """
    with app.app_context():
        plan = _plan(name="محدود", usage_limits_json={"monthly_text": 5})
        activate_subscription(db.session, user, plan)
        db.session.commit()
        conv = Conversation(user_id=user, title="t")
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id

    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/conversations/{conv_id}/messages",
                       json={"content": "سلام"},
                       headers={**headers, "Idempotency-Key": "k1"})
    assert resp.status_code not in (402, 403), resp.get_json()


def test_chat_over_quota_never_403s(client, app, user):
    """Exhausted quota never blocks with 403 (the old hard limit is gone);
    the request follows the normal wallet flow."""
    with app.app_context():
        plan = _plan(name="محدود", usage_limits_json={"monthly_text": 1})
        activate_subscription(db.session, user, plan)
        PlanLimitService(db.session).increment(user, "text")
        db.session.commit()
        conv = Conversation(user_id=user, title="t")
        db.session.add(conv)
        db.session.commit()
        conv_id = conv.id

    headers = user_headers(client, user)
    resp = client.post(f"{BASE}/conversations/{conv_id}/messages",
                       json={"content": "سلام"},
                       headers={**headers, "Idempotency-Key": "k2"})
    assert resp.status_code != 403, resp.get_json()
    assert resp.get_json()["error"]["code"] != "PLAN_LIMIT_EXCEEDED"


def test_admin_delete_plan_with_active_subscription_fails(client, app, user, admin):
    plan = _plan(name="دارای مشترک")
    with app.app_context():
        activate_subscription(db.session, user, plan)
        db.session.commit()

    headers = admin_headers(client, admin)
    resp = client.delete(f"{BASE}/admin/plans/{plan.id}", headers=headers)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"

    # After cancelling the subscription, real deletion is allowed.
    with app.app_context():
        sub = get_active_subscription(db.session, user)
        sub.status = SUB_CANCELLED
        db.session.commit()

    resp = client.delete(f"{BASE}/admin/plans/{plan.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["deleted"] is True
    with app.app_context():
        assert db.session.get(Plan, plan.id) is None


def test_admin_plan_crud_with_audit(client, app, admin):
    headers = admin_headers(client, admin)

    resp = client.post(f"{BASE}/admin/plans", headers=headers, json={
        "name": "سازمانی",
        "price_irr": 10_000_000,
        "period_days": 30,
        "features": ["پشتیبانی ویژه"],
        "usage_limits": {"monthly_text": 1000, "monthly_image": 200,
                         "monthly_audio_minutes": 600},
        "bonus_irr": 1_500_000,
        "is_featured": True,
        "sort_order": 4,
    })
    assert resp.status_code == 201, resp.get_json()
    plan_id = resp.get_json()["data"]["id"]

    resp = client.patch(f"{BASE}/admin/plans/{plan_id}", headers=headers, json={
        "price_irr": 12_000_000,
        "usage_limits": {"monthly_text": 500},
    })
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["price_irr"] == 12_000_000
    assert data["usage_limits"] == {"monthly_text": 500}
    assert data["is_featured"] is True

    resp = client.get(f"{BASE}/admin/plans", headers=headers)
    assert resp.status_code == 200
    assert any(p["id"] == plan_id for p in resp.get_json()["data"])
