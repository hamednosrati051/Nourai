# Nourai Backend — «نورا»

Flask 3 application-factory backend for the Nourai Persian AI assistant.
Python 3.12 · SQLAlchemy 2 · Alembic · MySQL 8.4 (utf8mb4/UTC) · Redis ·
Celery · Pydantic v2.

## Quick start (Docker Compose, from the repo root)

```bash
docker compose up --build
```

The compose file lives at the repository root (`~/workspace/nourai/`); the
backend `Dockerfile` here builds the `api`/`worker` images with Gunicorn.

## Local development

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
cp .env.example .env   # then fill in secrets
```

Run the API:

```bash
.venv/bin/python -m flask --app app:create_app run
```

Run the Celery worker (image/audio jobs):

```bash
.venv/bin/celery -A app.tasks.celery_app.celery worker --loglevel=info
```

## Database

Migrations target **MySQL 8.4** (utf8mb4, UTC, naive datetimes with
microsecond precision):

```bash
DATABASE_URL="mysql+pymysql://user:pass@host:3306/nourai" .venv/bin/alembic upgrade head
```

> SQLite is used only for the test suite. The full migration does not run
> end-to-end on SQLite because the deferred `assets ↔ generation_jobs`
> foreign key is added with `ALTER TABLE`, which SQLite does not support
> (works on MySQL).

## Admin bootstrap & demo seed

```bash
# one-time admin (env vars ADMIN_BOOTSTRAP_USERNAME / ADMIN_BOOTSTRAP_PASSWORD)
.venv/bin/flask --app app:create_app create-admin

# dev/test demo data: 4 subscription plans + demo catalog (never in prod)
APP_ENV=development .venv/bin/flask --app app:create_app seed-demo
```

`seed-demo` creates the plans «رایگان» (free, monthly limits
20 texts / 2 images), «پایه», «حرفه‌ای» (featured, «پیشنهاد ما», with a
300,000 IRR wallet bonus), «سازمانی». Prices are placeholders and are
fully editable via the admin API.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

`tests/test_plans.py` covers: public plan catalog visibility/ordering,
free-plan activation without payment, `PAYMENT_REQUIRED` for paid plans,
the paid-plan purchase flow (plan price forced → fake Zibal verify →
wallet credit + subscription), plan-limit rejection at the API level,
deletion of a plan with an active subscription, and admin plan CRUD.

## Subscription plans

- `plans`: `price_irr` (canonical IRR; toman display only in UI),
  `period_days` (e.g. 30), Persian `features_json`, nullable
  `usage_limits_json` (e.g. `{"monthly_text": 50, "monthly_image": 5,
  "monthly_audio_minutes": 10}`), `bonus_irr` (promotional wallet credit
  for paid plans), `is_free` / `is_featured` («پیشنهاد ما») / `is_active`,
  `sort_order`.
- `user_plan_subscriptions`: at most one **active** subscription per user
  (enforced in `services/plans.py`); `expires_at` is computed from
  `period_days`; period usage counters reset naturally because every
  (re)activation starts a fresh subscription row.
- `POST /api/v1/plans/{id}/activate`: free + active plans activate
  directly (no payment). Paid plans answer `PAYMENT_REQUIRED` (402); the
  client must buy through `POST /api/v1/payments` with `plan_id`.
- `POST /api/v1/payments` with `plan_id`: the amount is **forced** to the
  plan's `price_irr` — the client's amount is never trusted. Free plans
  are rejected here (use direct activation).
- After a successful Zibal verification the wallet receives **two**
  separate, auditable ledger entries: a `deposit` of `price_irr` and a
  `bonus` of `bonus_irr`, and the plan subscription is activated.
- `GET /api/v1/me/plan`: current active plan + period limits + usage.
- Admin: `GET/POST/PATCH/DELETE /api/v1/admin/plans[/{id}]` with audit
  logs. `DELETE` fails with `409` while any active subscription references
  the plan (deactivate first); otherwise the row is really deleted.

## Plan usage limits

`PlanLimitService` (`app/services/plans.py`) is consulted on every AI
request (text / image / audio). If the user has an active subscription
whose plan defines `usage_limits_json`, the current-period counter is
checked **before** the request is accepted; exceeding the quota returns
`PLAN_LIMIT_EXCEEDED` (403) with a Persian message. Successful generations
increment the counters afterwards (audio counts billable minutes,
`ceil(duration/60)`). Expired subscriptions are lazily marked `expired`
and impose no limits. Users without a subscription are unlimited (MVP
fair-use only).

## Conventions & assumptions

- UUIDs are `CHAR(36)` strings everywhere; datetimes are naive UTC with
  microsecond precision; money is integer IRR only (never float).
- Uniform envelopes: `{"data", "meta", "request_id"}` on success,
  `{"error": {"code", "message"}, "request_id"}` on failure; user-facing
  messages are Persian. Pagination uses `page`/`page_size` (max 100).
- OTP values, API keys, and raw provider responses are never logged.
- SMS.ir / Zibal field mappings are taken from the official docs only;
  where a mapping is not confirmed, the code carries an explicit TODO and
  the fake adapters raise in production (`APP_ENV=production`).
- Fake SMS/payment providers refuse to run in production.
- `POST /payments` defaults its idempotency key to
  `payreq-{user_id}-{amount}` when the client omits `Idempotency-Key`.
- Chat message idempotency keys are stored in usage metadata (not yet
  enforced as unique constraints) — see code comments.
