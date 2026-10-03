"""Prompt blocklist: normalization, matching, kill switch, job hook."""
from __future__ import annotations

from app.extensions import db
from app.models import User
from app.models.moderation import ModerationSettings, PromptBlocklist
from app.services.prompt_filter import find_blocked_phrase, normalize_text
from tests.conftest import user_headers


def test_normalize_persian():
    # Arabic kaf/yeh -> Persian, ZWNJ + tatweel stripped, collapsed.
    assert normalize_text("سِکس") == normalize_text("سکس")
    assert normalize_text("سـکس") == "سکس"
    assert normalize_text("كيس") == "کیس"
    assert normalize_text("SEX") == "sex"
    assert normalize_text("  a   b ") == "a b"


def test_ascii_substring_match(app):
    with app.app_context():
        db.session.add(PromptBlocklist(phrase="sex", is_active=True))
        db.session.commit()
        assert find_blocked_phrase(db.session, "a sexy picture") == "sex"
        assert find_blocked_phrase(db.session, "SEXUAL content") == "sex"
        assert find_blocked_phrase(db.session, "a sunset") is None


def test_persian_word_boundary(app):
    with app.app_context():
        db.session.add(PromptBlocklist(phrase="سکس", is_active=True))
        db.session.commit()
        assert find_blocked_phrase(db.session, "عکس سکس") == "سکس"
        # Obfuscation attempts still match after normalization.
        assert find_blocked_phrase(db.session, "عکس سـکس") == "سکس"
        assert find_blocked_phrase(db.session, "عکس سِكس") == "سکس"  # Arabic kaf
        assert find_blocked_phrase(db.session, "سکسکه نوزاد") is None


def test_inactive_phrase_ignored(app):
    with app.app_context():
        db.session.add(PromptBlocklist(phrase="sex", is_active=False))
        db.session.commit()
        assert find_blocked_phrase(db.session, "sexy") is None


def test_kill_switch_disables(app):
    with app.app_context():
        db.session.add(PromptBlocklist(phrase="sex", is_active=True))
        db.session.add(ModerationSettings(prompt_filter_enabled=False))
        db.session.commit()
        assert find_blocked_phrase(db.session, "sexy") is None


def test_image_job_blocked_prompt(app, client, user):
    with app.app_context():
        db.session.add(PromptBlocklist(phrase="سکس", is_active=True))
        db.session.commit()
    headers = {**user_headers(client, user), "Idempotency-Key": "blocked-1"}
    r = client.post(
        "/api/v1/image/jobs", headers=headers, json={"prompt": "یک عکس سکس"}
    )
    assert r.status_code == 422
    body = r.get_json()
    assert body["error"]["code"] == "PROMPT_BLOCKED"


def test_image_job_clean_prompt_passes_filter(app, client, user):
    # With an empty blocklist the filter is a no-op; the request proceeds
    # to the normal model-availability check.
    headers = {**user_headers(client, user), "Idempotency-Key": "clean-1"}
    r = client.post(
        "/api/v1/image/jobs", headers=headers, json={"prompt": "یک گربه"}
    )
    assert r.get_json()["error"]["code"] != "PROMPT_BLOCKED"
