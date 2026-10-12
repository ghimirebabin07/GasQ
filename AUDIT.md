# GasQ Phase 1 Audit

Date: 2026-10-11

Scope: full source-code audit of the current GasQ project at `D:\MY WORKSPACE\GasQ`.

This phase only inspected the code and wrote the audit. No implementation fixes were made in this phase.

## Files Reviewed

- `README.md`
- `requirements.txt`
- `CURRENT_CODE_STATUS.md`
- `backend/auth.py`
- `backend/database.py`
- `backend/main.py`
- `backend/models/dealer.py`
- `backend/models/customer.py`
- `backend/models/token.py`
- `backend/routers/customer.py`
- `backend/routers/dealer.py`
- `backend/routers/queue.py`
- `backend/schemas/customer.py`
- `backend/schemas/dealer.py`
- `backend/schemas/token.py`
- `backend/services/queue_service.py`
- `backend/tests/test_dealer_credentials.py`
- `frontend/index.html`
- `frontend/customer.html`
- `frontend/dealers.html`
- `frontend/dealer-dashboard.html`
- `frontend/queue.html`
- `frontend/css/style.css`
- `frontend/js/customer.js`
- `frontend/js/dealer.js`
- `frontend/js/queue.js`

## Executive Summary

GasQ is still a local prototype, not a secure deployable real-world application.

The biggest risks are:

- Customers have no real authentication.
- Queue token ownership is not protected.
- Anyone who knows a token ID can view or cancel it.
- One-active-token business rules are wrong and not enforced at database level.
- Stock is not reserved atomically, so overselling and race-condition bugs are possible.
- Dealer accounts are active immediately with no admin approval.
- Sessions are bearer tokens in `localStorage`, with no refresh-token rotation, revocation, CSRF strategy, or customer/admin roles.
- There is no notification system.
- There is no audit log.
- There is no deployable production architecture, migrations, Docker, CI, or environment configuration.

## Findings

### 1. Customer has no real authentication

- Severity: Critical
- File: `backend/routers/customer.py:11`
- File: `frontend/customer.html:17`
- File: `frontend/js/customer.js:68`

The customer "login" is just name and phone. There is no Google login, email OTP, session, token, or identity proof. Anyone can create or reuse a customer record by phone number.

Impact:

- Customer identity can be hijacked.
- Token history cannot be trusted.
- Notifications cannot be private.
- Queue abuse is easy.

Required direction:

- Add customer auth with Google ID token verification and optional email OTP.
- Store customer sessions securely.

### 2. Existing customer record can be overwritten by anyone with the phone number

- Severity: Critical
- File: `backend/routers/customer.py:14`
- File: `backend/routers/customer.py:16`

If a phone number already exists, the API updates the customer name and returns the same customer. There is no authentication or verification.

Impact:

- Attacker can take over another customer's local identity by entering their phone number.
- Dealer sees attacker-controlled name for an existing phone.

Required direction:

- Require authenticated customer session before updating profile.
- Treat phone as unverified until verification/auth policy is implemented.

### 3. Token status is public by token ID

- Severity: Critical
- File: `backend/routers/queue.py:42`
- File: `backend/routers/queue.py:43`
- File: `frontend/js/queue.js:32`

`GET /queue/{token_id}` has no authentication or ownership check.

Impact:

- Anyone can enumerate token IDs and see customer queue data indirectly.
- Current queue and dealer status can leak.

Required direction:

- Require customer owner, dealer owner, or admin role.

### 4. Token cancellation is public by token ID

- Severity: Critical
- File: `backend/routers/queue.py:47`
- File: `backend/routers/queue.py:48`
- File: `backend/services/queue_service.py:165`

`POST /queue/{token_id}/cancel` has no customer ownership check.

Impact:

- Anyone who knows or guesses a token ID can cancel another customer's token.

Required direction:

- Require authenticated customer owner or admin.

### 5. One-active-token rule is wrong

- Severity: Critical
- File: `backend/services/queue_service.py:84`
- File: `backend/services/queue_service.py:87`
- File: `backend/services/queue_service.py:88`

The app only blocks duplicate active tokens for the same customer at the same dealer. It does not block a customer from joining Shop B while already active in Shop A.

Impact:

- Violates the most important business rule.
- Customers can hold multiple active tokens across shops.

Required direction:

- Query active token by customer across all dealers.
- Return clear error naming the existing shop.
- Enforce at database level with partial unique index.

### 6. Active token rule is not enforced at database level

- Severity: Critical
- File: `backend/models/token.py:18`
- File: `backend/models/token.py:21`
- File: `backend/models/token.py:25`

There is no partial unique index for active tokens. There is no unique constraint for active token by customer or phone.

Impact:

- Race conditions can create multiple active tokens.
- Double-clicks or parallel requests can bypass code-level checks.

Required direction:

- Add migrations.
- Add partial unique index on active `customer_id`.
- Add partial unique index on active phone once phone is stored on token or joined through a properly modeled reservation.
- Add concurrency test.

### 7. Token creation is not transactional or race-safe

- Severity: Critical
- File: `backend/services/queue_service.py:84`
- File: `backend/services/queue_service.py:99`
- File: `backend/services/queue_service.py:105`
- File: `backend/services/queue_service.py:106`

The code checks for an existing token, calculates the next token number, inserts, and commits without row locks or database constraints.

Impact:

- Parallel requests can create duplicate active tokens.
- Parallel requests can create duplicate token numbers.

Required direction:

- Use database transaction boundaries.
- Use constraints and handle integrity errors.
- For PostgreSQL, use proper isolation/locking strategy.

### 8. No stock reservation when a token is created

- Severity: Critical
- File: `backend/services/queue_service.py:78`
- File: `backend/services/queue_service.py:99`
- File: `backend/services/queue_service.py:143`
- File: `backend/services/queue_service.py:145`

Stock is decremented only when a token is served. A dealer with 1 cylinder can hand out many waiting tokens.

Impact:

- Overselling.
- Customer receives token for unavailable stock.
- Queue length can exceed actual supply.

Required direction:

- Reserve stock atomically at token creation or maintain reserved stock separately.
- Release reservation on cancel/no-show/expiry.

### 9. Queue join allows out-of-stock dealers

- Severity: High
- File: `backend/services/queue_service.py:78`
- File: `backend/services/queue_service.py:79`
- File: `backend/services/queue_service.py:99`

`create_token` only verifies the dealer exists. It does not check active status, stock, open/closed state, or queue limit.

Impact:

- Customers can join dealers with zero stock.
- Customers can join inactive/deleted dealers if they know the ID.

Required direction:

- Check approved/active/open dealer status.
- Check available/reservable stock.
- Check queue limit.

### 10. Dealer approval workflow does not exist

- Severity: High
- File: `backend/models/dealer.py:21`
- File: `backend/routers/dealer.py:90`
- File: `backend/routers/dealer.py:99`
- File: `backend/routers/dealer.py:69`
- File: `backend/routers/dealer.py:71`

Dealers have only `is_active`. Registration sets `is_active=True`, and public listing shows every active dealer. There is no `pending / approved / suspended` status.

Impact:

- Fake dealer shops can appear publicly immediately.
- No admin review.

Required direction:

- Add dealer status enum.
- Only approved dealers appear publicly.
- Add admin approval/suspension routes.

### 11. Admin role does not exist

- Severity: High
- File: `backend/auth.py:63`
- File: `backend/routers/dealer.py:83`
- File: `backend/routers/dealer.py:146`

There is no user table, role table, admin model, or admin route.

Impact:

- No way to approve dealers.
- No way to view audit logs.
- No operational control.

Required direction:

- Introduce users/roles or separate admin model.
- Add RBAC dependencies.

### 12. Dealer auth is not real production session auth

- Severity: High
- File: `backend/auth.py:55`
- File: `backend/auth.py:60`
- File: `frontend/js/dealer.js:17`
- File: `frontend/js/dealer.js:18`

Dealer sessions are custom signed bearer strings stored in `localStorage`. There are no short-lived JWTs, no refresh tokens, no rotation, no server-side revocation, and logout only deletes local storage.

Impact:

- Stolen tokens remain valid until expiry.
- XSS can steal tokens from `localStorage`.
- Cannot revoke sessions server-side.

Required direction:

- Use access JWT plus hashed rotating refresh token.
- Prefer httpOnly secure cookies with CSRF protection.
- Store refresh token records in DB and revoke on logout.

### 13. Runtime-generated secret invalidates all tokens after restart

- Severity: Medium
- File: `backend/auth.py:15`

If `LPG_QUEUE_SECRET_KEY` is absent, a new random secret is generated at process start.

Impact:

- All sessions break on restart.
- Multi-process deployments cannot validate each other's tokens.

Required direction:

- Require `SECRET_KEY` in non-dev environments.
- Load config from `.env`.

### 14. No `.env`, `.env.example`, or typed config

- Severity: High
- File: `requirements.txt:1`
- File: `backend/database.py:7`
- File: `backend/auth.py:15`
- File: `backend/main.py:16`

Configuration is hardcoded in modules. There is no pydantic-settings config layer and no environment-specific settings.

Impact:

- Cannot safely deploy to production.
- Secrets and URLs are not centrally managed.
- CORS and database cannot be changed cleanly per environment.

Required direction:

- Add `backend/app/core/config.py` or equivalent.
- Add `.env.example`.
- Add settings for DB, CORS, JWT, Google, SMTP, OTP, phone OTP, etc.

### 15. CORS allows every origin with credentials

- Severity: High
- File: `backend/main.py:16`
- File: `backend/main.py:18`
- File: `backend/main.py:19`

`allow_origins=["*"]` with `allow_credentials=True` is unsafe and unsuitable for production.

Impact:

- Broad browser access from unknown origins.
- Dangerous once cookies or authenticated endpoints are added.

Required direction:

- Read allowed origins from config.
- Lock to the real frontend domain in production.

### 16. Manual SQLite migration in startup is unsafe

- Severity: High
- File: `backend/main.py:33`
- File: `backend/main.py:38`
- File: `backend/main.py:40`
- File: `backend/main.py:45`

Schema changes are handled by raw SQLite `ALTER TABLE` statements during startup.

Impact:

- Not safe for production.
- No versioned migrations.
- Not portable to PostgreSQL.
- Startup can fail if indexes conflict or DB state is unexpected.

Required direction:

- Add Alembic migrations.
- Remove manual startup migrations.

### 17. SQLite is hardcoded

- Severity: High
- File: `backend/database.py:7`
- File: `backend/database.py:8`
- File: `backend/database.py:10`

The database URL always points to `backend/lpg_queue.db`.

Impact:

- Cannot deploy cleanly with PostgreSQL.
- Tests cannot easily use isolated DB via config.
- Production concurrency is weak.

Required direction:

- Use `DATABASE_URL` from config.
- PostgreSQL for production.
- SQLite only for local/dev/test.

### 18. No health or readiness endpoints

- Severity: Medium
- File: `backend/main.py:116`
- File: `backend/main.py:121`

The app has no `/health` or `/ready`.

Impact:

- Deploy platforms cannot reliably check service health.
- CI smoke checks are harder.

Required direction:

- Add `/health` for process health.
- Add `/ready` for DB readiness.

### 19. No consistent error format

- Severity: Medium
- File: `backend/routers/customer.py:11`
- File: `backend/routers/dealer.py:83`
- File: `backend/routers/queue.py:36`
- File: `backend/services/queue_service.py:93`

Errors are plain FastAPI defaults or inconsistent `detail` strings.

Impact:

- Frontend cannot reliably render validation and business-rule errors.
- Harder to test.

Required direction:

- Add error-handling middleware with standard shape.

### 20. No rate limiting

- Severity: High
- File: `backend/routers/dealer.py:83`
- File: `backend/routers/dealer.py:110`
- File: `backend/routers/customer.py:11`

Register/login/customer creation endpoints have no rate limit.

Impact:

- Brute-force login attempts.
- Dealer spam.
- Customer record spam.

Required direction:

- Add `slowapi` or similar.
- Rate-limit auth, register, OTP endpoints.

### 21. Password hashing should use Argon2 or bcrypt as required

- Severity: Medium
- File: `backend/auth.py:20`
- File: `backend/auth.py:22`
- File: `requirements.txt:1`

Current password hashing uses PBKDF2. It is better than plaintext, but the target requirement asks for argon2 or bcrypt.

Impact:

- Does not meet stated target.
- PBKDF2 may be acceptable only as interim.

Required direction:

- Add `argon2-cffi` or `passlib[bcrypt]`.
- Migrate password hashes safely.

### 22. Dealer login uses username, not email

- Severity: Medium
- File: `backend/models/dealer.py:14`
- File: `backend/schemas/dealer.py:31`
- File: `backend/routers/dealer.py:84`
- File: `frontend/dealer-dashboard.html:32`

The target requirement says dealers register/login with email + password. Current implementation uses `username`.

Impact:

- Does not meet required auth design.
- No email verification or contact identity.

Required direction:

- Add dealer email field.
- Use email as login identifier.
- Decide whether username remains display-only.

### 23. Google login is absent

- Severity: High
- File: `backend/auth.py:1`
- File: `backend/routers/customer.py:11`
- File: `backend/routers/dealer.py:110`

There is no Google Identity Services frontend integration or backend ID-token verification.

Impact:

- Required customer and optional dealer Google login are missing.

Required direction:

- Add Google client config.
- Backend verifies signature, audience, issuer, expiry, and `email_verified`.
- Tests must mock Google keys.

### 24. Email OTP flow is absent

- Severity: High
- File: `backend/models/customer.py:9`
- File: `backend/routers/customer.py:11`
- File: `requirements.txt:1`

There is no OTP model, hashing, expiry, attempts, lockout, cooldown, hourly limit, mail provider, or SMTP config.

Impact:

- Required zero-cost fallback auth is missing.

Required direction:

- Add OTP table/service.
- Add ConsoleProvider and SMTP provider.
- Add rate limits and tests.

### 25. Phone validation is not Nepal-specific

- Severity: Medium
- File: `backend/schemas/customer.py:8`
- File: `backend/schemas/dealer.py:50`
- File: `frontend/customer.html:26`
- File: `frontend/dealer-dashboard.html:64`

The code allows 7-15 digits with optional `+`. Requirement asks for Nepal format: `+977` and 10 digits starting with `97` or `98`.

Impact:

- Invalid Nepal mobile numbers are accepted.
- Business data quality is poor.

Required direction:

- Normalize and validate Nepal mobile numbers.
- Store phone verification status.

### 26. Phone is not stored as unverified

- Severity: Medium
- File: `backend/models/customer.py:14`
- File: `backend/models/dealer.py:19`

There is no `phone_verified` or `phone_status` field.

Impact:

- Dealer cannot know whether phone was verified.
- Future SMS verification will require schema changes.

Required direction:

- Add `phone_verified=False`.
- Add `PHONE_OTP_ENABLED=false` config and SMS provider interface.

### 27. Token states do not match required business states

- Severity: High
- File: `backend/models/token.py:10`
- File: `backend/models/token.py:13`
- File: `backend/models/token.py:14`

Current states are `WAITING`, `CALLED`, `SERVED`, `SKIPPED`, `CANCELLED`. Required states are `waiting -> called -> completed | no_show | cancelled | expired`.

Impact:

- Missing no-show and expired behavior.
- State names differ from target.
- "Skipped" is ambiguous and does not release/handle stock.

Required direction:

- Define canonical state machine.
- Add transition validator/service.
- Migrate data.

### 28. Invalid state transitions are only partially blocked

- Severity: High
- File: `backend/services/queue_service.py:133`
- File: `backend/services/queue_service.py:151`
- File: `backend/services/queue_service.py:165`

Only serve/skip/cancel have basic checks. There is no central transition matrix and no audit.

Impact:

- Hard to prove queue correctness.
- Future states can break rules.

Required direction:

- Centralize state transitions.
- Reject invalid transitions consistently.

### 29. Called tokens never expire

- Severity: High
- File: `backend/models/token.py:27`
- File: `backend/services/queue_service.py:126`

There is `called_at`, but no background job to mark called tokens as `no_show` after X minutes.

Impact:

- Dealer queue can get stuck.
- Stock reservation release cannot happen.

Required direction:

- Add APScheduler job.
- Configurable default 15 minutes.
- Add no-show transition and stock release.

### 30. Token numbers are not per dealer per day

- Severity: Medium
- File: `backend/services/queue_service.py:69`
- File: `backend/services/queue_service.py:71`

Token number uses max token number for all time per dealer.

Impact:

- Does not reset daily.
- Does not meet business rule.

Required direction:

- Add `token_date` or use date-part index.
- Unique `(dealer_id, date, token_number)`.

### 31. No audit log for stock or token changes

- Severity: High
- File: `backend/services/queue_service.py:126`
- File: `backend/services/queue_service.py:143`
- File: `backend/services/queue_service.py:159`
- File: `backend/services/queue_service.py:170`
- File: `backend/services/queue_service.py:181`

State and stock changes happen with no audit table.

Impact:

- Cannot trace dealer actions.
- Admin cannot investigate disputes.

Required direction:

- Add audit log model/service.
- Record actor, action, old value, new value, timestamp.

### 32. Stock update overwrites total instead of add/remove with reason

- Severity: Medium
- File: `backend/services/queue_service.py:176`
- File: `backend/services/queue_service.py:181`
- File: `frontend/dealer-dashboard.html:96`

Dealer enters a new absolute stock number. Requirement asks add/remove with reason and never negative.

Impact:

- No trace of why stock changed.
- Mistakes are hard to audit.

Required direction:

- Add stock adjustment endpoint with delta and reason.
- Store stock movement history.

### 33. No open/closed shop status

- Severity: High
- File: `backend/models/dealer.py:9`
- File: `backend/schemas/dealer.py:10`
- File: `backend/services/queue_service.py:78`

Dealer model has no open/closed field. Queue join cannot block closed shops.

Impact:

- Customers can take tokens from closed shops.

Required direction:

- Add `is_open`.
- Dealer dashboard open/close control.
- Queue join checks.

### 34. No queue limit

- Severity: Medium
- File: `backend/models/dealer.py:9`
- File: `backend/services/queue_service.py:78`

No field or check exists for max queue length.

Impact:

- Dealers cannot cap the queue.
- Customer expectations can be unrealistic.

Required direction:

- Add `queue_limit`.
- Enforce during token creation.

### 35. No cylinder type support

- Severity: Medium
- File: `backend/models/dealer.py:20`
- File: `backend/schemas/dealer.py:17`

Only one integer stock field exists. Requirement asks cylinders available by type, e.g. 14.2kg.

Impact:

- Cannot represent multiple LPG cylinder products.

Required direction:

- Add stock item/product model.

### 36. Dealer public listing does not include required fields

- Severity: Medium
- File: `backend/schemas/dealer.py:10`
- File: `backend/routers/dealer.py:22`
- File: `frontend/js/customer.js:79`

Public list lacks open/closed, cylinder type, estimated wait, area search fields, approval status, and queue limit.

Impact:

- Customer listing is too basic for real use.

Required direction:

- Extend dealer read schema after model changes.

### 37. No search/filter/nearest dealer support

- Severity: Medium
- File: `backend/routers/dealer.py:69`
- File: `frontend/dealers.html:15`
- File: `frontend/js/customer.js:113`

The app lists all active dealers only.

Impact:

- Poor UX for real users.

Required direction:

- Add query params for area, availability, and lat/lng nearest.
- Add frontend search controls.

### 38. No notifications model or API

- Severity: High
- File: `backend/models/__init__.py:1`
- File: `backend/routers/dealer.py:199`
- File: `backend/services/queue_service.py:111`

No notification table, service, route, unread count, SSE, WebSocket, or polling fallback exists.

Impact:

- Customer does not get notified when token is called except manual refresh.

Required direction:

- Add notifications table.
- Create notification on call-next.
- Add owner-only read routes.

### 39. No real-time updates

- Severity: Medium
- File: `frontend/js/queue.js:24`
- File: `frontend/js/queue.js:61`

Queue status requires manual refresh. No SSE/WebSocket/polling fallback is implemented.

Impact:

- Customers may miss called tokens.

Required direction:

- Add SSE or WebSocket.
- Add polling fallback.

### 40. No notification idempotency

- Severity: Medium
- File: `backend/services/queue_service.py:111`

Since notifications are absent, there is no uniqueness/idempotency rule.

Impact:

- Future retry logic could duplicate notifications.

Required direction:

- Add idempotency key or unique constraint per event.

### 41. No token history page/API

- Severity: Medium
- File: `backend/routers/queue.py:1`
- File: `frontend/queue.html:1`

There is no customer token history endpoint or frontend page.

Impact:

- Required customer feature missing.

Required direction:

- Add owner-authenticated token history.

### 42. No dealer history or daily summary

- Severity: Medium
- File: `backend/routers/dealer.py:157`
- File: `frontend/dealer-dashboard.html:75`

Dashboard only shows current active queue and stock.

Impact:

- Dealer cannot review past tokens or daily totals.

Required direction:

- Add history and daily summary endpoints/views.

### 43. Dealer can delete/deactivate shop without re-authentication

- Severity: Medium
- File: `frontend/dealer-dashboard.html:102`
- File: `frontend/js/dealer.js:325`
- File: `backend/routers/dealer.py:146`

Delete uses a browser confirm only. It does not require password confirmation, reason, admin flow, or audit log.

Impact:

- Stolen session can deactivate shop.
- No trace of why shop disappeared.

Required direction:

- Require re-auth or strong confirmation.
- Audit action.
- Consider suspend instead of delete.

### 44. Dealer registration has no email/phone uniqueness check beyond username

- Severity: Medium
- File: `backend/routers/dealer.py:85`
- File: `backend/routers/dealer.py:86`
- File: `backend/models/dealer.py:19`

Only username uniqueness is checked. Same phone and shop name can be reused.

Impact:

- Duplicate/fake dealer records.

Required direction:

- Add email login.
- Add uniqueness or admin duplicate review policy.

### 45. Seed dealers cannot log in

- Severity: Medium
- File: `backend/main.py:51`
- File: `backend/main.py:53`
- File: `backend/main.py:60`
- File: `backend/main.py:68`

Seed dealers are created without username/password. They appear publicly but have no owner account.

Impact:

- Public demo dealers cannot be managed through login.
- Customer can join queues that no dealer can control after auth change.

Required direction:

- Create dev-only seed users safely or mark seed data clearly.

### 46. Public dealers can include unowned legacy dealers

- Severity: Medium
- File: `backend/routers/dealer.py:69`
- File: `backend/routers/dealer.py:71`
- File: `backend/models/dealer.py:14`
- File: `backend/models/dealer.py:15`

The list does not require `username` or `password_hash`. Legacy seeded dealers remain public.

Impact:

- Shops can appear with no authenticated owner.

Required direction:

- Approved dealer listing should require verified owner account and status approved.

### 47. Pydantic validation is too restrictive for Nepali names and addresses

- Severity: Low
- File: `backend/schemas/customer.py:7`
- File: `backend/schemas/dealer.py:48`
- File: `backend/schemas/dealer.py:49`

Regexes only allow ASCII names/addresses.

Impact:

- Nepali names or local address text cannot be entered.

Required direction:

- Decide language policy.
- Support Unicode safely if needed.

### 48. Frontend validation duplicates backend validation manually

- Severity: Low
- File: `frontend/js/dealer.js:4`
- File: `frontend/js/customer.js:2`
- File: `backend/schemas/dealer.py:31`
- File: `backend/schemas/customer.py:6`

Regex rules are duplicated in JS and Python.

Impact:

- Rules can drift.
- Bugs appear when one side changes.

Required direction:

- Keep backend as source of truth.
- Consider generated schema docs or shared constants where practical.

### 49. Frontend uses `localStorage` for auth/session data

- Severity: High
- File: `frontend/js/dealer.js:12`
- File: `frontend/js/dealer.js:17`
- File: `frontend/js/customer.js:7`
- File: `frontend/js/customer.js:72`

Dealer token and customer identity are stored in `localStorage`.

Impact:

- XSS can steal dealer token.
- Customer identity can be modified by the user or attacker.

Required direction:

- Use httpOnly secure cookies for refresh tokens.
- Store only non-sensitive UI state client-side.

### 50. Customer identity is trusted from browser localStorage

- Severity: Critical
- File: `frontend/js/customer.js:7`
- File: `frontend/js/customer.js:101`
- File: `backend/routers/queue.py:36`
- File: `backend/routers/queue.py:37`

Queue join sends `customer_id` from localStorage. Backend accepts it without authentication.

Impact:

- Anyone can request tokens as any customer ID.

Required direction:

- Backend must derive customer identity from authenticated session, not request body.

### 51. Token ID is trusted from URL/localStorage

- Severity: High
- File: `frontend/js/queue.js:1`
- File: `frontend/js/queue.js:3`
- File: `backend/routers/queue.py:42`
- File: `backend/routers/queue.py:47`

Queue page reads token ID from URL or localStorage and calls public endpoints.

Impact:

- Token IDs are not private.
- URL sharing or guessing allows status/cancel access.

Required direction:

- Owner-authenticated "my token" endpoint.

### 52. API assumes all responses are JSON

- Severity: Low
- File: `frontend/js/customer.js:35`
- File: `frontend/js/dealer.js:127`
- File: `frontend/js/queue.js:17`

The frontend always calls `response.json()`.

Impact:

- Network/proxy/HTML error responses can break error handling.

Required direction:

- Add safe response parsing and generic network error handling.

### 53. Buttons do not prevent double-submit

- Severity: Medium
- File: `frontend/js/customer.js:96`
- File: `frontend/js/dealer.js:213`
- File: `frontend/js/dealer.js:236`
- File: `frontend/js/dealer.js:283`

Forms and queue actions do not disable buttons while requests are in flight.

Impact:

- Double-clicks can create duplicate requests.
- Race conditions are more likely.

Required direction:

- Disable buttons during pending requests.
- Backend must still enforce idempotency/constraints.

### 54. Queue join does not disable Get Token after click

- Severity: Medium
- File: `frontend/js/customer.js:96`
- File: `frontend/js/customer.js:99`

`Get Token` can be clicked repeatedly before navigation.

Impact:

- Duplicate token requests.

Required direction:

- Disable button after first click.
- Add server-side idempotency.

### 55. `innerHTML` is still used for user-influenced content

- Severity: Medium
- File: `frontend/js/customer.js:83`
- File: `frontend/js/dealer.js:169`
- File: `frontend/js/dealer.js:161`

Some values are escaped manually, but the pattern is fragile. One static message uses `innerHTML` too.

Impact:

- Future changes can introduce XSS.
- Manual escaping is easy to miss.

Required direction:

- Prefer DOM node creation and `textContent`.
- Avoid `innerHTML` for dynamic content.

### 56. No security headers

- Severity: Medium
- File: `backend/main.py:14`

No middleware sets security headers such as CSP, X-Frame-Options, Referrer-Policy, X-Content-Type-Options.

Impact:

- Weaker browser security.

Required direction:

- Add security headers middleware.
- Configure CSP carefully for static frontend and Google login.

### 57. No HTTPS enforcement for production

- Severity: Medium
- File: `backend/main.py:14`

There is no production HTTPS setting, proxy awareness, secure cookie strategy, or HSTS.

Impact:

- Tokens/cookies would be unsafe if deployed incorrectly.

Required direction:

- Document and enforce HTTPS in production.
- Add deployment proxy config.

### 58. No structured logging or request IDs

- Severity: Low
- File: `backend/main.py:14`

The backend uses default Uvicorn/FastAPI behavior.

Impact:

- Harder to debug production incidents.
- No request tracing.

Required direction:

- Add request ID middleware.
- Add structured logs.

### 59. No background worker

- Severity: Medium
- File: `requirements.txt:1`
- File: `backend/main.py:105`

APScheduler or another worker mechanism is not installed/configured.

Impact:

- Cannot expire called tokens.
- Cannot send reminders.

Required direction:

- Add APScheduler and worker module.

### 60. No production dependency stack

- Severity: Medium
- File: `requirements.txt:1`

Dependencies include only FastAPI, Uvicorn, SQLAlchemy, Pydantic. Missing pydantic-settings, Alembic, auth libraries, JWT, Google auth, email provider libs if needed, rate limiting, pytest/httpx, coverage, ruff, mypy/pyright, pip-audit.

Impact:

- Cannot meet target architecture or testing requirements.

Required direction:

- Add dependencies in controlled phases.

### 61. No pytest/httpx integration tests

- Severity: High
- File: `backend/tests/test_dealer_credentials.py:1`

Only a small unittest file exists for credential validation.

Impact:

- Queue/auth/security regressions are untested.
- No test DB isolation.

Required direction:

- Add pytest suite with test database.
- Add route/service tests.

### 62. No concurrency test

- Severity: Critical
- File: `backend/tests/test_dealer_credentials.py:1`
- File: `backend/services/queue_service.py:78`

There is no test proving only one active token can be created under parallel requests.

Impact:

- Core business guarantee is unproven and currently broken.

Required direction:

- Add concurrent test with many parallel requests.
- Fix constraints before expecting it to pass.

### 63. No Playwright tests

- Severity: Medium
- File: `frontend/`

There are no frontend E2E tests.

Impact:

- Login, queue, dealer flows can break unnoticed.

Required direction:

- Add Playwright tests for customer and dealer flows.

### 64. No linting/type-checking config

- Severity: Low
- File: `requirements.txt:1`

No Ruff, mypy, pyright, eslint, or config files exist.

Impact:

- Code quality relies on manual review.

Required direction:

- Add basic lint/type tooling.

### 65. No pip-audit setup

- Severity: Low
- File: `requirements.txt:1`

No dependency vulnerability audit tooling exists.

Impact:

- Known vulnerable dependencies may go unnoticed.

Required direction:

- Add `pip-audit` to dev tooling or CI.

### 66. No Dockerfile or docker-compose

- Severity: Medium
- File: project root

No Dockerfile or compose file exists.

Impact:

- Cannot verify clean deployment.
- No free-tier friendly production packaging.

Required direction:

- Add backend Dockerfile.
- Add compose for API + Postgres + reverse proxy/static frontend.

### 67. No CI workflow

- Severity: Medium
- File: project root

No GitHub Actions workflow exists.

Impact:

- Tests do not run automatically.

Required direction:

- Add CI for lint, tests, frontend syntax checks.

### 68. No deployment documentation

- Severity: Medium
- File: project root

There is no `DEPLOY.md`.

Impact:

- App is not deployable by repeatable instructions.

Required direction:

- Add free-tier deployment guide.

### 69. README is outdated

- Severity: Low
- File: `README.md:6`
- File: `README.md:36`
- File: `README.md:51`

README still describes the old dealer selector flow and unauthenticated dealer endpoints.

Impact:

- New users will run wrong commands and follow broken demo flow.

Required direction:

- Rewrite README after architecture/API stabilizes.

### 70. No `.gitignore`

- Severity: Medium
- File: project root

No `.gitignore` appears in the source list.

Impact:

- `.venv`, `__pycache__`, `.env`, and SQLite DB files may be committed.

Required direction:

- Add `.gitignore`.

### 71. Database file is inside backend directory

- Severity: Low
- File: `backend/database.py:7`

SQLite DB lives at `backend/lpg_queue.db`.

Impact:

- Easy to commit runtime data.
- Tests can mutate dev database.

Required direction:

- Use configurable DB URL and separate dev/test DB paths.

### 72. `backend/.venv` exists and can confuse commands

- Severity: Low
- File: `backend/.venv`

There is a nested environment directory under `backend`. The required environment is root `.venv`.

Impact:

- Developers may activate/install into the wrong environment.
- Compile/test commands may scan the wrong directory.

Required direction:

- Ignore/remove only with user approval.
- Document root `.venv` usage.

### 73. Frontend JS is not modular

- Severity: Low
- File: `frontend/js/customer.js:1`
- File: `frontend/js/dealer.js:1`
- File: `frontend/js/queue.js:1`

API helpers and auth logic are duplicated across files.

Impact:

- Bugs and validation drift.
- Harder to maintain.

Required direction:

- Split into `api.js`, `auth.js`, `notifications.js`, page modules.

### 74. No accessibility pass

- Severity: Low
- File: `frontend/*.html`
- File: `frontend/css/style.css`

Basic labels exist, but there is no visible focus styling beyond browser defaults, no ARIA live region for async messages, and no notification badge.

Impact:

- Users with assistive tech may have poor experience.

Required direction:

- Add accessible status regions and keyboard/focus testing.

### 75. Dealer dashboard lacks loading states

- Severity: Low
- File: `frontend/js/dealer.js:187`
- File: `frontend/js/dealer.js:213`
- File: `frontend/js/dealer.js:283`

Requests do not show loading states.

Impact:

- Users may double-click or think the app is broken.

Required direction:

- Add disabled/loading states for every action.

### 76. Queue page lacks auto-refresh or live updates

- Severity: Medium
- File: `frontend/queue.html:39`
- File: `frontend/js/queue.js:61`

Customer must manually click refresh.

Impact:

- Missed token calls.

Required direction:

- Add SSE/WebSocket or polling fallback.

### 77. API route naming is inconsistent

- Severity: Low
- File: `backend/routers/dealer.py:69`
- File: `backend/routers/dealer.py:83`
- File: `backend/routers/dealer.py:157`

Routes mix `/dealers`, `/dealer/me`, and `/dealer/{dealer_id}`.

Impact:

- Harder API documentation and client maintenance.

Required direction:

- Version API under `/api/v1`.
- Use consistent plural resources.

### 78. Static frontend and API are not separated

- Severity: Low
- File: `backend/main.py:30`
- File: `backend/main.py:121`

FastAPI serves frontend pages and API in same app with catch-all page route.

Impact:

- Can complicate production routing and API versioning.

Required direction:

- Keep for dev if desired, but production should serve static frontend via CDN/proxy or clear static route.

### 79. Catch-all page route can hide bad URLs

- Severity: Low
- File: `backend/main.py:121`
- File: `backend/main.py:126`

Unknown `.html` pages return `index.html` instead of 404.

Impact:

- Broken URLs can look successful.

Required direction:

- Return proper 404 for unknown pages unless intentionally SPA fallback.

### 80. Token ownership is not modeled

- Severity: High
- File: `backend/models/token.py:22`
- File: `backend/models/token.py:23`

Token belongs to dealer and customer but has no snapshot of customer phone, reservation, or auth owner/session.

Impact:

- Phone-level uniqueness across accounts is impossible with current token schema.
- Historical token data can change if customer profile changes.

Required direction:

- Store phone snapshot and reservation fields on token or a related table.

### 81. `served_at` field name will not fit completed/no-show/expired model

- Severity: Low
- File: `backend/models/token.py:28`

Only `served_at` exists. Required states need completed/no-show/cancelled/expired timestamps.

Impact:

- Poor auditability and state tracking.

Required direction:

- Add state-specific timestamps or transition log.

### 82. `skip_token` does not call next or requeue

- Severity: Medium
- File: `backend/services/queue_service.py:151`
- File: `backend/services/queue_service.py:159`

Skipping changes status to `SKIPPED` and stops. There is no explicit no-show, no stock release, no next-token call, no audit.

Impact:

- Dealer flow is incomplete.

Required direction:

- Define skip/no-show behavior.
- Possibly call next separately with transition audit.

### 83. Serving consumes stock too late and can go negative under race

- Severity: High
- File: `backend/services/queue_service.py:140`
- File: `backend/services/queue_service.py:145`

The code checks stock and decrements in application logic without atomic database update.

Impact:

- Two parallel serves could oversell in a real concurrent DB scenario.

Required direction:

- Use atomic update with `WHERE available_cylinders > 0`.
- Prefer reservation model.

### 84. No database CHECK constraint for stock

- Severity: High
- File: `backend/models/dealer.py:20`

`available_cylinders` has no DB-level `CHECK >= 0`.

Impact:

- Bugs or direct SQL can store negative stock.

Required direction:

- Add DB check constraint via migration.

### 85. No foreign-key cascade/on-delete policy

- Severity: Low
- File: `backend/models/token.py:22`
- File: `backend/models/token.py:23`

Foreign keys have no explicit cascade/restrict behavior.

Impact:

- Future deletes can fail or leave unclear semantics.

Required direction:

- Define deletion/suspension policy. Prefer not deleting core records.

### 86. SQLite foreign keys may not be enforced

- Severity: Medium
- File: `backend/database.py:10`

SQLite requires `PRAGMA foreign_keys=ON`; the engine does not enable it.

Impact:

- Invalid references may be possible in local/dev DB.

Required direction:

- Enable FK pragma for SQLite.
- Use PostgreSQL in production.

### 87. No request body size or input abuse protection

- Severity: Low
- File: `backend/main.py:14`

There is no middleware/proxy config limiting request size.

Impact:

- Potential resource abuse.

Required direction:

- Configure reverse proxy and app limits.

### 88. Login error timing/user enumeration not considered

- Severity: Low
- File: `backend/routers/dealer.py:112`
- File: `backend/routers/dealer.py:113`

Missing-user path returns without password hash verification. Response text is generic, but timing may differ.

Impact:

- Minor username enumeration risk.

Required direction:

- Use dummy hash verification for missing users if needed.
- Add rate limiting first.

### 89. Dealer password rule allows only ASCII and limited symbols

- Severity: Low
- File: `backend/schemas/dealer.py:7`
- File: `backend/schemas/dealer.py:33`

This may be acceptable, but should be explicitly documented.

Impact:

- Some strong password manager-generated passwords may be rejected.

Required direction:

- Decide policy and align frontend/backend/tests.

### 90. Tests do not verify auth routes

- Severity: High
- File: `backend/tests/test_dealer_credentials.py:1`
- File: `backend/routers/dealer.py:83`
- File: `backend/routers/dealer.py:110`

Dealer register/login endpoints are not tested with HTTP client.

Impact:

- Auth flow can break while schema tests pass.

Required direction:

- Add pytest + httpx route tests with isolated DB.

### 91. Tests may import against local module path only

- Severity: Low
- File: `backend/tests/test_dealer_credentials.py:5`

Test imports `schemas.dealer` assuming current working directory is `backend`.

Impact:

- Tests may fail from project root depending on Python path.

Required direction:

- Package backend properly or configure pytest path.

### 92. No frontend auth guard for customer token ownership

- Severity: High
- File: `frontend/js/queue.js:1`
- File: `frontend/js/customer.js:113`

Frontend only checks local token ID. It cannot prove the current user owns the token.

Impact:

- UI can display/cancel wrong token if localStorage is edited.

Required direction:

- Add authenticated `GET /customer/me/token`.

### 93. No account recovery or password reset

- Severity: Medium
- File: `backend/routers/dealer.py:110`

Dealers can register/login but cannot reset forgotten passwords.

Impact:

- Real users can get locked out.

Required direction:

- Add email-based reset after email identity exists.

### 94. No email verification for dealers

- Severity: Medium
- File: `backend/routers/dealer.py:83`

Dealer does not provide email at all.

Impact:

- No trusted contact method.
- No approval communication.

Required direction:

- Add verified email model/flow.

### 95. No Google OAuth frontend integration

- Severity: High
- File: `frontend/customer.html:17`
- File: `frontend/dealer-dashboard.html:29`

Frontend has no Google Identity Services script or login button.

Impact:

- Required login path missing.

Required direction:

- Add Google button and ID token submission.

### 96. No phone OTP provider interface

- Severity: Low
- File: `backend/`

No `PHONE_OTP_ENABLED` flag or SMS provider exists.

Impact:

- Future SMS verification requires redesign.

Required direction:

- Add config and stub provider.

### 97. No email provider abstraction

- Severity: Medium
- File: `backend/`

No mail package/service exists.

Impact:

- Email OTP cannot be implemented cleanly.

Required direction:

- Add mail provider interface with console and SMTP providers.

### 98. No API prefix creates collision risk with frontend paths

- Severity: Low
- File: `backend/main.py:24`
- File: `backend/main.py:121`

API routes live at root alongside frontend pages.

Impact:

- Future route/page names can collide.

Required direction:

- Prefix APIs under `/api`.

### 99. No deployment artifacts

- Severity: Medium
- File: project root

Missing `Dockerfile`, `docker-compose.yml`, `DEPLOY.md`, CI, production server config.

Impact:

- Definition of done cannot be met.

Required direction:

- Add deploy artifacts in later phase.

### 100. `CURRENT_CODE_STATUS.md` can become stale

- Severity: Low
- File: `CURRENT_CODE_STATUS.md:1`

Status file records runtime PIDs and current state, which can become stale quickly.

Impact:

- Developers may trust outdated port/process info.

Required direction:

- Keep status docs either generated or remove volatile runtime data from committed docs.

## Short Phase Plan

### Phase 1: Audit

Status: completed by this document.

Output:

- `AUDIT.md`

No code fixes in this phase.

### Phase 2: Stabilize local project hygiene and test foundation

Recommended next work:

- Add `.gitignore`.
- Add `.env.example`.
- Add config module.
- Add pytest/httpx test setup with isolated test DB.
- Add lint/test commands.
- Update README enough to run current app correctly.

### Phase 3: Correct core queue rules

Recommended next work:

- Rework token model/state machine.
- Enforce one active token across all shops.
- Add database-level constraints.
- Add stock reservation.
- Add concurrency test.

### Phase 4: Real authentication and roles

Recommended next work:

- Add customer auth: Google OIDC verification and email OTP fallback.
- Add dealer email/password auth with approval status.
- Add admin role.
- Add JWT/refresh-token sessions or secure cookie strategy.
- Add rate limiting.

### Phase 5: Dealer/customer product features

Recommended next work:

- Dealer open/close.
- Stock adjustments with reason.
- Token history.
- Dealer daily summary.
- Search/filter/nearest dealer.

### Phase 6: Notifications and background jobs

Recommended next work:

- Notification table and routes.
- SSE/WebSocket or polling fallback.
- Call-next notification.
- No-show expiry worker.
- Reminder jobs.

### Phase 7: Production architecture and deployment

Recommended next work:

- Alembic migrations.
- PostgreSQL support.
- Dockerfile and docker-compose.
- CI.
- DEPLOY.md.
- Security headers.
- Health/readiness endpoints.

## Stop Point

Per instruction, this phase stops after writing the audit. Wait for the user to say `continue` before starting Phase 2.
