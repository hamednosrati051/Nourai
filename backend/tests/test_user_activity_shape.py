"""Admin user activity endpoint returns the Paginated<ActivityItem> shape."""
from app.extensions import db
from app.models import AuditLog
from tests.conftest import admin_headers


def test_user_activity_paginated_shape(app, client, admin, user):
    uid = user if isinstance(user, str) else user.id
    with app.app_context():
        db.session.add(AuditLog(actor_type="user", actor_id=uid, action="user.login"))
        db.session.add(AuditLog(actor_type="user", actor_id=uid, action="image.job_created"))
        db.session.commit()
    r = client.get(f"/api/v1/admin/users/{uid}/activity",
                   headers=admin_headers(client, admin))
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert set(data.keys()) == {"items", "meta"}
    assert data["meta"]["total_items"] == 2
    by_action = {i["title"]: i for i in data["items"]}
    login = by_action["user.login"]
    assert login["kind"] == "login"
    assert login["created_at"]
    assert login["id"]
    assert by_action["image.job_created"]["kind"] == "ai_request"


def test_user_activity_empty(app, client, admin, user):
    uid = user if isinstance(user, str) else user.id
    r = client.get(f"/api/v1/admin/users/{uid}/activity",
                   headers=admin_headers(client, admin))
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["items"] == []
    assert data["meta"]["total_items"] == 0
