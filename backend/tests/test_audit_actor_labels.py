"""Audit log rows carry a human-readable actor_label (no raw ids needed)."""
from app.extensions import db
from app.models import AdminUser, AuditLog
from tests.conftest import admin_headers


def test_audit_log_actor_labels(app, client, admin, user):
    admin_id = admin if isinstance(admin, str) else admin.id
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        db.session.add(AuditLog(actor_type="admin", actor_id=admin_id, action="user.disabled"))
        db.session.add(AuditLog(actor_type="user", actor_id=uid, action="user.login"))
        db.session.commit()
    r = client.get("/api/v1/admin/audit-logs", headers=admin_headers(client, admin))
    assert r.status_code == 200
    items = {i["action"]: i for i in r.get_json()["data"]["items"]}
    assert items["user.disabled"]["actor_label"] == "admin"
    # user mobile 989121234567 masked -> 0915***5367 style, never the raw id
    assert items["user.login"]["actor_label"] != uid
    assert "***" in items["user.login"]["actor_label"]
