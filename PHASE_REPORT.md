# GasQ Phase Reports - Consolidated

This document consolidates all phase reports from Phase 2 through Phase 13.

---

## Phase 1: Initial Audit (Completed 2026-10-11)

Full source-code audit identifying 100 critical security, business logic, and production-readiness issues. See `AUDIT.md` for complete findings.

**Key Issues Identified:**
- No real customer authentication
- Queue token ownership not protected
- One-active-token rule not enforced at database level
- No stock reservation (overselling possible)
- No dealer approval workflow
- No audit logs or notifications
- No production deployment architecture

---

## Phase 2: Project Hygiene & Test Foundation (Completed 2026-10-11)

**Changes:**
- Added `.gitignore`, `.env.example`, `ASSUMPTIONS.md`
- Added `backend/config.py` with pydantic-settings
- Updated `backend/database.py` to read `GASQ_DATABASE_URL` and enable SQLite foreign keys
- Updated `backend/auth.py` to read token secret/TTL from settings
- Updated `backend/main.py` for configured CORS and `/health`, `/ready` endpoints
- Added `backend/tests/conftest.py` for isolated test databases
- Added `backend/tests/test_api_smoke.py`
- Added `pydantic-settings`, `pytest`, `httpx` dependencies

**Test Results:** 11 passed

**Remaining:** Core queue business rules still broken

---

## Phase 3: Core Queue Rules (Completed 2026-10-11)

**Changes:**
- Added `Token.customer_phone` for phone-level uniqueness
- Created SQLite partial unique indexes:
  - `ux_tokens_active_customer` on `customer_id` WHERE status IN ('WAITING', 'CALLED')
  - `ux_tokens_active_phone` on `customer_phone` WHERE status IN ('WAITING', 'CALLED')
- Implemented stock reservation at token creation (not at serve)
- Cancel/skip now releases reserved stock
- Added `backend/tests/test_queue_rules.py` with concurrency test

**Test Results:** 16 passed

**Remaining:** Customer auth, admin approval, notifications, Alembic/PostgreSQL still missing

---

## Phase 4: Admin & Dealer Approval (Completed 2026-10-11)

**Changes:**
- Added role-aware signed access tokens
- Added `Dealer.email` and `Dealer.status` (PENDING/APPROVED/SUSPENDED)
- Added environment-configured admin login (`GASQ_ADMIN_EMAIL`, `GASQ_ADMIN_PASSWORD`)
- Added admin endpoints:
  - `POST /admin/login`
  - `GET /admin/dealers`
  - `POST /admin/dealers/{id}/approve`
  - `POST /admin/dealers/{id}/suspend`
- Public dealer list now shows only approved dealers
- Pending dealers can login but cannot operate queue endpoints

**Test Results:** 20 passed

**Remaining:** Customer auth, Google login, email OTP, refresh tokens, audit logs, notifications

---

## Phase 5: Audit Logs & Notifications (Completed 2026-10-11)

**Changes:**
- Added `backend/models/audit_log.py` and `backend/services/audit_service.py`
- Added `backend/models/notification.py` and `backend/services/notification_service.py`
- Added audit logging for: dealer approval/suspension, token creation/call/serve/skip/cancel, stock updates
- Added notification creation when dealer calls token (with idempotency key)
- Added admin endpoints: `GET /admin/audit-logs`, `GET /admin/notifications`

**Test Results:** 22 passed

**Remaining:** Customer auth, Google login, email OTP, refresh tokens, Alembic/PostgreSQL

---

## Phase 6: Customer Authentication (Completed 2026-10-11)

**Changes:**
- Added `customers.password_hash` field
- Added customer auth endpoints:
  - `POST /customer/register`
  - `POST /customer/login`
  - `GET /customer/me`
  - `GET /customer/notifications`
- Updated queue endpoints to require customer Bearer token:
  - `POST /queue/join` no longer trusts `customer_id` from browser
  - `GET /queue/{token_id}` requires owning customer
  - `POST /queue/{token_id}/cancel` requires owning customer
- Updated frontend customer flow with password support and authenticated requests

**Test Results:** 23 passed

**Remaining:** Google login, email OTP, refresh tokens, Alembic/PostgreSQL, Docker/CI

---

## Phase 7: Startup & Timestamp Cleanup (Completed 2026-10-11)

**Changes:**
- Replaced deprecated `@app.on_event("startup")` with lifespan context manager
- Added `backend/time_utils.py` with shared UTC timestamp helper
- Replaced all `datetime.utcnow()` calls with `utc_now()` helper
- Updated timestamp defaults in all models

**Test Results:** 23 passed, 1 warning (third-party Starlette deprecation)

**Remaining:** Google login, email OTP, refresh tokens, Alembic/PostgreSQL, Docker/CI

---

## Phase 8: Database-Backed Admin (Completed 2026-10-11)

**Changes:**
- Added `backend/models/admin_user.py` with `AdminUser` model
- Admin login now verifies against stored password hash (not direct env comparison)
- Startup seeds first admin user from `GASQ_ADMIN_EMAIL`/`GASQ_ADMIN_PASSWORD`

**Test Results:** 23 passed

**Remaining:** Google login, email OTP, refresh tokens, Alembic/PostgreSQL, Docker/CI

---

## Phase 9: Secure Auth, Identity & Sessions (Completed 2026-10-11)

**Changes:**

1. **Google OpenID Connect (OIDC):**
   - `backend/services/google_auth_service.py` with `verify_google_id_token`
   - Validates signature, audience, issuer, expiration, `email_verified`
   - Endpoints: `POST /customer/auth/google`, `POST /dealer/auth/google`

2. **Email OTP Login:**
   - 6-digit code, SHA-256 hashed, stored in `email_otps` table
   - 5-minute validity, 60-second cooldown, max 5/hour, 5-attempt lockout
   - `MailProvider` interface with `ConsoleMailProvider` and `SmtpMailProvider`
   - Endpoints: `POST /customer/auth/otp/send`, `POST /customer/auth/otp/verify`

3. **Nepal Phone Validation:**
   - Regex: `+977` (optional) + 10 digits starting with `97` or `98`
   - `customers.is_phone_verified` field
   - Queue rule: cannot take token without phone
   - `SmsProvider` interface (console only, `GASQ_PHONE_OTP_ENABLED=false`)
   - Endpoint: `PUT /customer/phone`

4. **Password Hashing:**
   - Migrated to `bcrypt` (backwards-compatible with PBKDF2)

5. **Session Security:**
   - Short-lived PyJWT access tokens (HS256) with role, subject, jti
   - `backend/models/refresh_token.py` with SHA-256 hashed tokens
   - Endpoints: `POST /auth/refresh` (rotating), `POST /auth/logout`

6. **RBAC:**
   - Enforced with `get_current_customer`, `get_current_dealer`, `get_current_admin`

**Test Results:** 30 passed

---

## Phase 10: Real-Time Notifications & Background Worker (Completed 2026-10-11)

**Changes:**

1. **Background Worker (`backend/workers/scheduler.py`):**
   - `expire_no_show_tokens`: CALLED → NO_SHOW after 15 minutes, releases stock, creates notification
   - `check_and_send_position_reminders`: Reminder at position 3 (idempotent)
   - Async loop every 30 seconds via FastAPI lifespan (disabled during tests)

2. **Server-Sent Events (SSE):**
   - `NotificationBus` pub/sub with asyncio queues
   - `GET /customer/notifications/stream` with Bearer or `?token=` auth
   - 15-second heartbeat

3. **Notification Read State:**
   - `GET /customer/notifications/unread-count`
   - `POST /customer/notifications/{id}/read`

4. **Token Status Updates:**
   - Added `NO_SHOW`, `EXPIRED`, `COMPLETED` to `TokenStatus`

**Test Results:** 33 passed

---

## Phase 11: Frontend Modularization & Real-Time UI (Completed 2026-10-11)

**Changes:**

1. **Modular Frontend Architecture:**
   - `frontend/js/api.js`: Unified HTTP client with auto Bearer injection, 401 interception, silent refresh
   - `frontend/js/auth.js`: Session lifecycle, auth guards, Google Sign-in, Email OTP, Nepal phone modal
   - `frontend/js/notifications.js`: SSE client, auto-reconnect, unread badge, notification drawer, Web Audio chime
   - `frontend/js/customer.js`: Multi-tab auth, dealer discovery, queue entry with phone validation
   - `frontend/js/queue.js`: Real-time queue tracker with SSE updates
   - `frontend/js/dealer.js`: Dealer portal with approval status, metrics, no-show action

2. **Backend Endpoints Added:**
   - `GET /auth/config`: Returns `{ google_client_id, phone_otp_enabled }`
   - `GET /customer/tokens`: Token history (last 50)
   - `GET /customer/tokens/active`: Active queue status
   - `POST /dealer/{id}/token/{id}/no-show`: Mark called token as NO_SHOW, restore stock

**Test Results:** 36 passed

---

## Phase 12: Alembic Migrations & PostgreSQL Readiness (Completed 2026-10-11)

**Changes:**
- Installed `alembic==1.20.0`, `psycopg2-binary==2.9.13`
- Initialized `backend/alembic/` with custom `env.py`:
  - Dynamic `database_url` from config
  - Auto `postgres://` → `postgresql://` normalization
  - `render_as_batch=True` for SQLite/PostgreSQL compatibility
- Added declarative partial unique indexes to `Token` model with `postgresql_where`/`sqlite_where`
- Created baseline migration `c94d2a648be7_initial_schema.py` covering all 8 tables
- Replaced manual SQLite migrations with `run_db_migrations()` calling `alembic.command.upgrade`

**Test Results:** 36 passed

---

## Phase 13: QA, Test Coverage & Playwright E2E (Completed 2026-10-11)

**Changes:**

1. **Static Analysis & Security:**
   - Configured `pyproject.toml` with `ruff` linting rules
   - Upgraded dependencies to fix CVEs: `pyjwt==2.15.1`, `starlette==1.7.0`, `fastapi==0.143.0`
   - `pip-audit`: No known vulnerabilities

2. **Code Coverage (85% Target):**
   - `routers/admin.py`: 87%
   - `routers/dealer.py`: 89%
   - `routers/queue.py`: 89%
   - `services/queue_service.py`: 88%
   - `workers/scheduler.py`: 85%
   - **Total: 85%**

3. **Playwright E2E Testing:**
   - `backend/tests/test_e2e_playwright.py`: Customer journey from landing → auth → dealer discovery → queue entry → dealer call → live status update
   - Test validates Nepal phone, token issuance, real-time SSE updates

**Test Results:** 37 passed (36 backend + 1 E2E)

---

## Current Status (After Phase 13)

**Completed Features:**
- Config-driven backend with pydantic-settings
- Customer auth: password, Google OIDC, email OTP
- Dealer auth: password, Google OIDC, email field, approval workflow
- Admin auth: database-backed with env-seeded first user
- Role-based access control (customer/dealer/admin)
- Rotating refresh tokens with revocation
- Nepal phone validation with SMS provider interface
- Queue rules: one active token across all shops, database-enforced
- Stock reservation at token creation, release on cancel/no-show
- Audit logs for all major actions
- Real-time notifications via SSE with unread badge
- Background worker: 15-minute no-show expiry, position-3 reminders
- Alembic migrations (SQLite + PostgreSQL compatible)
- 85% backend test coverage
- Playwright E2E testing
- Zero known dependency vulnerabilities

**Production Deployment Ready:**
- `Dockerfile` and `docker-compose.yml` (FastAPI + PostgreSQL)
- `.github/workflows/ci.yml` (lint, test, build)
- `DEPLOY.md` with zero-cost architecture guide (Neon + Render)
- All environment variables documented in `.env.example`

**Next Steps:**
- Deploy to production (user will handle deployment)
- Monitor and iterate based on real-world usage

---

## Assumptions (From Phase 2)

1. Root `.venv` is the only supported local environment; `backend/.venv` is stray/ignored
2. Local dev uses SQLite; production uses PostgreSQL
3. Phase 2 did not fix queue business rules (fixed in Phase 3)
4. Dealer bearer tokens kept initially; secure sessions added in Phase 9
5. `GASQ_SECRET_KEY` from `.env`; runtime-generated if missing (dev only)
6. CORS origins as comma-separated string in `.env` for Windows PowerShell compatibility
