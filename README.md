# LPG Gas Digital Queue Management System

GasQ is a FastAPI + SQLite + plain HTML/CSS/JavaScript project for managing LPG dealer queues.

This repository is currently being upgraded from a local prototype into a secure deployable application. See `AUDIT.md` for the current issue list and `ASSUMPTIONS.md` for decisions made during the upgrade.

## Features

- Customer registration/login with phone number and password
- Active dealer list with stock, people waiting, and current serving token
- Digital queue token creation and manual refresh tracking
- Customer token cancellation while still waiting
- Dealer registration/login
- Admin login, dealer approval/suspension, audit logs, and notification records
- Authenticated customer queue status, cancellation, and notification access
- Basic in-memory API rate limiting
- Dealer-owned dashboard with stock updates, profile updates, queue list, Call Next, Serve, and Skip
- Health endpoints at `/health` and `/ready`
- SQLite database seeded with three LPG dealers and sample queue data
- Swagger/OpenAPI docs from FastAPI

## Project Structure

```text
backend/
  main.py
  database.py
  config.py
  auth.py
  models/
  schemas/
  routers/
  services/queue_service.py
  tests/
frontend/
  index.html
  customer.html
  dealers.html
  queue.html
  dealer-dashboard.html
  css/style.css
  js/
requirements.txt
requirements-dev.txt
README.md
```

## Windows PowerShell Setup

Use the root virtual environment only:

```powershell
cd "D:\MY WORKSPACE\GasQ"
.\.venv\Scripts\Activate.ps1
pip install -r .\requirements-dev.txt
```

Create a local `.env` from the example if needed:

```powershell
Copy-Item .env.example .env
```

Start the backend:

```powershell
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

If port `8000` is busy:

```powershell
uvicorn main:app --host 127.0.0.1 --port 8001
```

Open the app:

- Customer/dealer UI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health
- Readiness: http://127.0.0.1:8000/ready

The SQLite database file is created as `backend/lpg_queue.db` on first startup.

## Test Commands

Run backend tests:

```powershell
cd "D:\MY WORKSPACE\GasQ"
.\.venv\Scripts\python.exe -m pytest
```

Compile-check backend source:

```powershell
cd "D:\MY WORKSPACE\GasQ\backend"
..\.venv\Scripts\python.exe -m compileall -q main.py auth.py config.py database.py models routers schemas services tests
```

Check frontend JavaScript syntax:

```powershell
cd "D:\MY WORKSPACE\GasQ"
node --check frontend\js\customer.js
node --check frontend\js\dealer.js
node --check frontend\js\queue.js
```

## Demo Flow

1. Open http://127.0.0.1:8000
2. Choose "I'm a Customer"
3. Register or log in with name, phone number, and password
4. Choose "ABC LPG Dealer" and click "Get Token"
5. Refresh the queue page to see current serving token, people ahead, and status
6. Open http://127.0.0.1:8000/dealer-dashboard.html
7. Register a dealer account or log in as an existing registered dealer
8. Use the dealer dashboard to update stock and call/serve/skip tokens for that dealer

Note: the seeded demo dealers are visible to customers but do not currently have login credentials.

## Example API Requests

Register a customer:

```bash
curl -X POST http://127.0.0.1:8000/customer/register ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Ram Sharma\",\"phone\":\"9841000000\",\"password\":\"Customer123\"}"
```

Log in as a customer:

```bash
curl -X POST http://127.0.0.1:8000/customer/login ^
  -H "Content-Type: application/json" ^
  -d "{\"phone\":\"9841000000\",\"password\":\"Customer123\"}"
```

List dealers:

```bash
curl http://127.0.0.1:8000/dealers
```

Join a queue:

```bash
curl -X POST http://127.0.0.1:8000/queue/join ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer <customer access token>" ^
  -d "{\"dealer_id\":1}"
```

Check token status:

```bash
curl http://127.0.0.1:8000/queue/4 ^
  -H "Authorization: Bearer <customer access token>"
```

Dealer endpoints require login and a bearer token. The old unauthenticated examples below will return `401` unless you include:

```text
Authorization: Bearer <dealer access token>
```

Call next customer:

```bash
curl -X POST http://127.0.0.1:8000/dealer/1/call-next
```

Serve a called token:

```bash
curl -X POST http://127.0.0.1:8000/dealer/1/token/1/serve
```

Skip a called token:

```bash
curl -X POST http://127.0.0.1:8000/dealer/1/token/1/skip
```

Cancel a waiting token:

```bash
curl -X POST http://127.0.0.1:8000/queue/4/cancel ^
  -H "Authorization: Bearer <customer access token>"
```

Update stock:

```bash
curl -X PATCH http://127.0.0.1:8000/dealer/1/stock ^
  -H "Content-Type: application/json" ^
  -d "{\"available_cylinders\":42}"
```
