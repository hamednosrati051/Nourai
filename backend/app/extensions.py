"""Shared extension instances (created once, initialised in the app factory)."""
from __future__ import annotations

import logging
import threading
from typing import Any

from flask_sqlalchemy import SQLAlchemy

log = logging.getLogger(__name__)

db = SQLAlchemy()


class _InMemoryRateStore:
    """Process-local fixed-window store used when Redis is unavailable (tests)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}

    def hit(self, key: str, window_seconds: int) -> int:
        import time

        now = time.time()
        with self._lock:
            count, expires_at = self._buckets.get(key, (0, 0.0))
            if now >= expires_at:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._buckets[key] = (count, expires_at)
            return count


class _InMemoryKVStore:
    """Process-local key/value store with TTL, used when Redis is unavailable.

    Refresh-token revocation depends on get/setex; without a working fallback
    every /auth/refresh would 401 when Redis is down.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        import time

        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expires_at = item
            if time.time() >= expires_at:
                del self._data[key]
                return None
            return value

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        import time

        with self._lock:
            self._data[key] = (value, time.time() + ttl_seconds)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class RedisClient:
    """Thin wrapper: real Redis when reachable, in-memory fallback otherwise."""

    def __init__(self) -> None:
        self._client: Any | None = None
        self._memory = _InMemoryRateStore()
        self._kv_fallback = _InMemoryKVStore()
        self._attempted = False
        self._url = ""

    def init(self, url: str) -> None:
        self._url = url

    def _get(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._attempted:
            return None
        self._attempted = True
        try:
            import redis

            client = redis.Redis.from_url(self._url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            self._client = client
            log.info("connected to redis")
            return client
        except Exception as exc:  # noqa: BLE001 - fallback is intentional
            log.warning("redis unavailable, using in-memory fallback: %s", exc)
            return None

    # -- generic helpers -------------------------------------------------
    def get(self, key: str) -> str | None:
        client = self._get()
        if client is None:
            return self._kv_fallback.get(key)
        value = client.get(key)
        return value.decode() if isinstance(value, bytes) else value

    def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        client = self._get()
        if client is not None:
            client.setex(key, ttl_seconds, value)
        else:
            self._kv_fallback.setex(key, ttl_seconds, value)

    def delete(self, key: str) -> None:
        client = self._get()
        if client is not None:
            client.delete(key)
        else:
            self._kv_fallback.delete(key)

    def rate_limit_hit(self, key: str, window_seconds: int) -> int:
        """Increment a fixed-window counter, return the new count."""
        client = self._get()
        if client is None:
            return self._memory.hit(key, window_seconds)
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        return int(count)


redis_client = RedisClient()


def make_celery(flask_app=None):
    """Create the Celery application. Broker/backend come from REDIS_URL."""
    from celery import Celery

    from app.config import config

    celery = Celery("nourai", broker=config.redis_url, backend=config.redis_url)
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        beat_schedule={
            "sweep-stuck-jobs": {
                "task": "nourai.jobs.sweep_stuck",
                "schedule": 900.0,  # every 15 minutes
            },
        },
    )

    if flask_app is not None:
        class FlaskTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with flask_app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = FlaskTask

    return celery
