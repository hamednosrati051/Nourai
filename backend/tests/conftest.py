"""Shared pytest fixtures: in-memory SQLite app, test client, auth helpers."""
from __future__ import annotations

import pytest

from app import create_app
from app.auth.sessions import (
    ADMIN_ACCESS_COOKIE,
    ADMIN_CSRF_COOKIE,
    USER_ACCESS_COOKIE,
    USER_CSRF_COOKIE,
    create_access_token,
)
from app.extensions import db
from app.models import AdminUser, User


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_ENGINE_OPTIONS": {},
        }
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    """A verified, active user. Returns the user id (plain string)."""
    with app.app_context():
        u = User(mobile_normalized="989121234567", is_active=True)
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture()
def admin(app):
    """Returns the admin id (plain string)."""
    with app.app_context():
        a = AdminUser(username="admin", password_hash="x", is_active=True)
        db.session.add(a)
        db.session.commit()
        return a.id


def _set_cookies(client, access_cookie, csrf_cookie, subject, kind):
    token = create_access_token(subject, kind)
    client.set_cookie(access_cookie, token)
    client.set_cookie(csrf_cookie, "test-csrf-token")
    return {"X-CSRF-Token": "test-csrf-token"}


def user_headers(client, user_id: str) -> dict:
    """Authenticate *client* as a user; return headers for unsafe requests."""
    return _set_cookies(client, USER_ACCESS_COOKIE, USER_CSRF_COOKIE, user_id, "user")


def admin_headers(client, admin_id: str) -> dict:
    return _set_cookies(client, ADMIN_ACCESS_COOKIE, ADMIN_CSRF_COOKIE, admin_id, "admin")
