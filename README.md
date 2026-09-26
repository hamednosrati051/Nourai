# Nourai — «نورا»

Persian (RTL) AI platform: text chat, voice interaction and image generation —
with mobile-OTP login, wallet + Zibal payments, SMS.ir OTP delivery, a public
gallery of admin-approved generations, and a full admin panel.

> **English summary:** Nourai («نورا») is a Persian RTL AI-services web app.
> Flask 3 API + Next.js 14 frontend, MySQL 8.4, Redis/Celery, S3-compatible
> storage. Users sign in with mobile OTP (SMS.ir), top up a wallet (Zibal),
> and consume text / voice / image AI models with per-use, tiktoken-based
> billing. Admins manage users, payments, pricing, image-processing limits
> and the public gallery.

---

## معماری

```
Next.js 14 (App Router, TS, Tailwind 4.3, RTL, light/dark)
   │
   ▼
Flask 3 REST API (/api/v1) ── JWT in HttpOnly cookies, CSRF, rate limits
   ├── MySQL 8.4 (utf8mb4, UTC, ledger-based wallet)
   ├── Redis (OTP, rate limits, cache) + Celery workers (image/audio jobs)
   ├── S3/MinIO (private assets, short-lived signed URLs)
   ├── SMS.ir adapter (OTP)          ← production: SMS_PROVIDER=smsir
   ├── Zibal adapter (payments)      ← production: PAYMENT_PROVIDER=zibal
   └── AI provider adapters (text / STT / TTS / image) — swappable
```

ساختار مخزن:

```
nourai/
├── backend/            # Flask 3 app (application factory)
│   ├── app/            # api, auth, billing, providers, ai, services, tasks, models
│   ├── migrations/     # Alembic (initial migration: all tables)
│   ├── tests/          # pytest
│   └── Dockerfile
├── frontend/           # Next.js 14 App Router + Tailwind 4.3.3, fa/RTL
│   ├── app/            # /, /gallery, /auth/*, /dashboard/*, /admin/*
│   ├── components/ features/ lib/ types/
│   └── Dockerfile
├── infra/nginx/        # single-domain reverse proxy (prod profile)
├── docker-compose.yml
├── .env.example
└── README.md
```

## شروع سریع (development)

```bash
cp .env.example .env
# .env را ویرایش کنید؛ برای dev کافی است مقادیر پیش‌فرض بماند
# (SMS_PROVIDER=fake و PAYMENT_PROVIDER=fake فقط برای dev/test هستند)

docker compose up --build
```

سرویس‌ها:

| سرویس | آدرس |
|---|---|
| سایت | http://localhost:3000 |
| API | http://localhost:8000/api/v1/health |
| MinIO console | http://localhost:9001 |
| MySQL | localhost:3306 |

ساخت ادمین اولیه (از متغیرهای محیطی، بدون رمز hard-code):

```bash
docker compose exec backend flask create-admin
# uses ADMIN_BOOTSTRAP_USERNAME / ADMIN_BOOTSTRAP_PASSWORD from .env
```

اجرای migration و تست‌های backend:

```bash
docker compose exec backend flask db upgrade
docker compose exec backend pytest -q
```

اجرای محلی بدون داکر (backend):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
flask --app "app:create_app" db upgrade
flask --app "app:create_app" run
```

اجرای محلی frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

## پیکربندی مهم

- واحد پول canonical در backend همیشه **IRR** (عدد صحیح) است؛ تبدیل تومان/ریال فقط در `currency.ts` / `billing/currency.py`.
- `SMS_PROVIDER=smsir` و `PAYMENT_PROVIDER=zibal` فقط در production؛ مقادیر واقعی کلید SMS.ir، شناسه قالب، merchant زیبال و base URLها **فقط از environment** خوانده می‌شوند و هیچ endpoint/فیلدی حدس زده نشده است (TODOهای مشخص در `providers/sms_ir.py` و `providers/zibal.py` با ارجاع به مستندات رسمی).
- `FakeSmsProvider` / `FakePaymentGateway` در `APP_ENV=production` خطا می‌دهند و قابل فعال‌سازی نیستند.
- سقف‌های امنیتی تصویر (`IMAGE_UPLOAD_HARD_MAX_BYTES` و...) از environment می‌آیند و تنظیمات ادمین هرگز نمی‌تواند از آن‌ها بالاتر برود.

## API (خلاصه)

- `POST /api/v1/auth/otp/request` · `POST /api/v1/auth/otp/verify` · `POST /api/v1/auth/refresh` · `POST /api/v1/auth/logout` · `GET /api/v1/me`
- `GET /api/v1/wallet` · `GET /api/v1/wallet/transactions`
- `POST /api/v1/payments` · `GET /api/v1/payments/callback/zibal` (server-side verify, idempotent)
- `GET /api/v1/models` · conversations · `POST /api/v1/audio/jobs` · `POST /api/v1/image/jobs` (+ `/image/config`, `/image/estimate`) · `GET /api/v1/gallery` (max 20 approved) · `GET /api/v1/usage`
- `POST /api/v1/admin/auth/login` و همه `/api/v1/admin/*` (users, activity, assets, payments, gallery approve/reject, models, pricing-rules, image-processing settings, audit)

Envelope پاسخ: موفق `{data, meta, request_id}` و خطا `{error:{code,message}, request_id}`.

## Assumptions (فرض‌های ثبت‌شده)

- «فلکس» = Flask 3 (تأیید حامد).
- دیتابیس MySQL 8.4؛ UUID به‌صورت CHAR(36)؛ زمان‌ها UTC بدون timezone در DB.
- گالری عمومی حداکثر ۲۰ تصویر آخر تأییدشده (`reviewed_at` نزولی)؛ تصاویر ورودی چت و موارد pending/rejected هرگز عمومی نمی‌شوند؛ نام سازنده و prompt تا تعیین سیاست محصول نمایش داده نمی‌شوند.
- `tiktoken` فقط برای شمارش توکن **متن** است؛ هزینه تصویر/صوت از واحد واقعی همان سرویس (ابعاد، پیکسل، ثانیه) محاسبه می‌شود.
- نام برند «نورا» / Nourai در `frontend/lib/config.ts` متمرکز است.
- حذف خودکار محتوا فعال نیست (سیاست نگهداری هنوز تعیین نشده)؛ ساختار برای lifecycle آماده است.

## نقشه راه

- اتصال واقعی SMS.ir و زیبال با مستندات رسمی و credentialهای مالک (TODOها در adapterها).
- اتصال providerهای AI واسط (متن/صوت/تصویر) وقتی مستنداتشان رسید.
- Streaming پاسخ متنی (SSE)، 2FA ادمین، اپ موبایل — خارج از MVP.
