# Nourai (نورا) — Frontend

Next.js 14 (App Router) + TypeScript (strict) + Tailwind CSS 4.3.3 frontend for the
Nourai AI platform. Persian (fa), RTL, mobile-first, light/dark/system theme.

## Requirements

- Node.js 20+
- A running backend exposing the REST API under `/api/v1` (Flask, see repo root).

## Quick start (development)

```bash
cd frontend
cp .env.example .env.local   # optional; see "Environment variables"
npm install --no-audit --no-fund
npm run dev                  # http://localhost:3000
```

The dev server proxies nothing by itself: set `NEXT_PUBLIC_API_URL` to the backend
origin (e.g. `http://localhost:5000`) so API calls go to
`http://localhost:5000/api/v1/...`. In production the frontend and API sit behind
one reverse proxy, so `NEXT_PUBLIC_API_URL` can stay empty (same-origin `/api/v1`).

## Scripts

| Command            | What it does                          |
| ------------------ | ------------------------------------- |
| `npm run dev`      | Start the dev server                  |
| `npm run build`    | Production build                      |
| `npm start`        | Serve the production build            |
| `npm run lint`     | Next.js ESLint                        |
| `npm run type-check` | `tsc --noEmit` (strict)             |

## Environment variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `NEXT_PUBLIC_API_URL` | _(empty → same origin)_ | Backend origin, e.g. `http://localhost:5000`. The client appends `/api/v1`. |
| `NEXT_PUBLIC_USER_SESSION_COOKIE` | `nourai_user_session` | Cookie name the backend sets for user sessions. The middleware only checks presence; real auth is verified via `GET /api/v1/me`. |
| `NEXT_PUBLIC_ADMIN_SESSION_COOKIE` | `nourai_admin_session` | Same, for the admin session (`GET /api/v1/admin/me`). |

## Docker

```bash
cd frontend
docker build -t nourai-frontend .
docker run -p 3000:3000 nourai-frontend
```

Multi-stage build: `deps → builder → runner`. The runner uses Next.js
`standalone` output and runs as a non-root user. `NEXT_PUBLIC_*` values are baked
in at build time — pass them as `--build-arg` if they differ per environment.

## Project structure

```
frontend/
  app/                    # App Router pages
    page.tsx              # Home («نورا»): hero, service cards, plans, gallery carousel
    gallery/              # Public gallery, app style (max 20 approved images)
    auth/login|verify/    # Mobile + OTP sign-in
    dashboard/            # User panel: Binavira-style home (services, wallet,
                          # active-plan banner) + chat, voice, image, history,
                          # wallet, usage subpages
    admin/                # Admin panel: stats, users, payments, gallery, models,
                          # plans, pricing, image-settings, audit
    layout.tsx            # <html lang="fa" dir="rtl"> + no-flash theme script
    globals.css           # Tailwind v4 (@import "tailwindcss"; @theme tokens)
  components/             # Hand-rolled, RTL-friendly UI primitives
  features/               # react-query hooks per domain + QueryClient provider
  lib/                    # config, api client, currency, formatting, phone, theme
  types/api.ts            # Typed backend API contracts
  middleware.ts           # Cookie-presence guards for /dashboard/* and /admin/*
```

## Key conventions

- **Brand**: `BRAND = { fa: 'نورا', en: 'Nourai' }` in `lib/config.ts` — rename in one place.
- **Money**: backend stores integer IRR; UI shows toman. Convert only via `lib/currency.ts`.
- **Auth**: cookie-based (HttpOnly, set by backend). The frontend never stores tokens
  in localStorage. Mutations send the `csrf_token` cookie as `X-CSRF-Token`.
- **API envelope**: success `{ data, meta, request_id }` is unwrapped by `lib/api.ts`;
  errors `{ error: { code, message } }` become `ApiError` with Persian messages
  (`getErrorMessage`). 401 → login redirect (guards), 402 → top-up nudge,
  429 → retry hint.
- **Gallery**: the homepage carousel consumes *only* `GET /api/v1/gallery`
  (max 20 approved). Empty feed → real empty state, never placeholder images.
- **Plans**: the homepage pricing section renders *only* `GET /api/v1/plans`,
  ordered by `sort_order`. The free plan activates directly via
  `POST /api/v1/plans/{id}/activate`; paid plans go through the wallet top-up
  flow (`POST /api/v1/payments` with `plan_id`) and redirect to the gateway URL
  (Zibal) returned by the backend. Prices are stored in IRR and shown in toman.
  The plan with `is_featured` gets the «پیشنهاد ما» badge. The dashboard shows
  the «پلن فعال شما» banner from `GET /api/v1/me/plan`. The admin panel
  (`/admin/plans`) manages plans: name, toman price, period, features, limits,
  free/paid, featured, active/inactive, sort order; delete asks for confirmation.
- **Theme**: `light | dark | system`, persisted in localStorage, applied via
  `<html data-theme>` with a render-blocking init script (no flash). The dark
  theme is navy (`#0F172A` background, `#1E293B` cards); the light theme is full
  white. Custom utilities live in `app/globals.css` as Tailwind v4 `@utility`
  definitions (plain `@apply` of custom classes does not work in v4).
- **Floating navigation**: `/gallery` and `/dashboard` use the Binavira-inspired
  app style — a floating pill header plus a vertical right-side nav
  (`components/FloatingNav.tsx`, home / gallery / account). Hidden on mobile
  where it would collide with content; theme switching still applies.
- **A11y**: touch targets ≥ 44px, visible focus rings, `prefers-reduced-motion`
  respected (carousel autoplay off), Persian labels, WCAG AA contrast targets.

## Assumptions

- Backend follows the API contract in the spec (sections 8–10, 17), including the
  `{ data, meta, request_id }` / `{ error: { code, message } }` envelope shape.
- Session cookie names default to `nourai_user_session` / `nourai_admin_session`
  and are configurable (see above); the backend is the source of truth.
- OTP codes are 5 digits (`OTP_LENGTH` in `lib/config.ts`); the resend cooldown is
  120s (`OTP_RESEND_SECONDS`).
- Payment amounts are sent in integer IRR; the Zibal gateway unit contract lives
  in the backend adapter (never guessed here).
- Chat follows the spec: messages are read from `GET /api/v1/conversations/{id}`
  (the response is expected to embed a `messages` array; there is no separate
  GET `…/messages` endpoint), and sending uses `POST /api/v1/conversations/{id}/messages`.
- `GET /api/v1/me/plan` may return `{ plan: Plan | null }` or the plan directly;
  the frontend accepts both shapes.
- `next.config.mjs` allows remote images from any host for development; restrict
  `images.remotePatterns` to the storage/API hosts in production.
- `terms` and `privacy` footer links point to placeholder routes until the legal
  texts are provided.
