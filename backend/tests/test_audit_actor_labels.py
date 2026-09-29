"""Audit log rows carry human-readable actor/target labels and user search."""
from app.extensions import db
from app.models import AuditLog
from tests.conftest import admin_headers


def _seed(app, admin_id, uid):
    with app.app_context():
        db.session.add(AuditLog(actor_type="admin", actor_id=admin_id,
                                action="user.disabled",
                                target_type="user", target_id=uid))
        db.session.add(AuditLog(actor_type="user", actor_id=uid, action="user.login"))
        db.session.commit()


def test_audit_log_party_labels(app, client, admin, user):
    admin_id = admin if isinstance(admin, str) else admin.id
    uid = user if isinstance(user, str) else user.id
    _seed(app, admin_id, uid)
    r = client.get("/api/v1/admin/audit-logs", headers=admin_headers(client, admin))
    assert r.status_code == 200
    items = {i["action"]: i for i in r.get_json()["data"]["items"]}
    assert items["user.disabled"]["actor_label"] == "admin"
    # target user shown as masked mobile, not the raw id or "user"
    target_label = items["user.disabled"]["target_label"]
    assert target_label != uid and "***" in target_label
    assert items["user.login"]["actor_label"] != uid


def test_audit_log_search_by_mobile(app, client, admin):
    from app.auth.otp import normalize_mobile
    from app.models import User
    admin_id = admin if isinstance(admin, str) else admin.id
    with app.app_context():
        u = User(mobile_normalized=normalize_mobile("09121234567"), is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    _seed(app, admin_id, uid)
    h = admin_headers(client, admin)
    mobile = "09121234567"
    # actor OR target match
    r = client.get(f"/api/v1/admin/audit-logs?search={mobile}", headers=h)
    assert r.status_code == 200
    assert r.get_json()["data"]["meta"]["total_items"] == 2
    # unknown mobile -> empty
    r = client.get("/api/v1/admin/audit-logs?search=09000000000", headers=h)
    assert r.get_json()["data"]["meta"]["total_items"] == 0
