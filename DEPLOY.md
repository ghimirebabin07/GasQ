# GasQ Production Deployment Guide (Zero-Cost Architecture)

This guide provides step-by-step instructions to deploy GasQ to production at **$0.00/month** total operating cost using verified free-tier infrastructure.

---

## Architecture Overview (100% Free Tier)

| Component | Provider / Technology | Free Tier Limits | Cost |
| :--- | :--- | :--- | :--- |
| **Database** | [Neon.tech](https://neon.tech) Serverless PostgreSQL | 0.5 GB storage, auto-suspend, pooling | **$0.00** |
| **Backend API** | [Render.com](https://render.com) Web Service | 512 MB RAM, 0.1 CPU, auto-sleep on idle | **$0.00** |
| **Frontend UI** | Served directly via FastAPI StaticFiles | Bundled into backend container | **$0.00** |
| **Google Auth** | Google Identity Services (OpenID Connect) | Up to 50,000 monthly active users | **$0.00** |
| **Email OTP** | [Brevo](https://brevo.com) SMTP / Gmail App Password | 300 free transactional emails/day | **$0.00** |
| **Real-Time Queue**| Server-Sent Events (SSE) | Native HTTP stream (no external paid sockets) | **$0.00** |

---

## Step 1: Set Up Free PostgreSQL Database (Neon)

1. Sign up for a free account at [neon.tech](https://neon.tech).
2. Click **Create Project** and name it `gasq-production`.
3. In the project dashboard, select PostgreSQL version 16.
4. Copy the connection string. It will look similar to:
   ```text
   postgresql://gasq_owner:npg_xXyYzZ123@ep-cool-butterfly-123456.us-east-2.aws.neon.tech/gasq?sslmode=require
   ```
5. Save this URL for the `GASQ_DATABASE_URL` environment variable.

---

## Step 2: Set Up Google OAuth 2.0 Credentials (Optional / Recommended)

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project named **GasQ**.
3. Go to **APIs & Services** &rarr; **OAuth consent screen**:
   - Choose **External** user type.
   - Enter your App name (`GasQ`), support email, and developer email.
   - Under Scopes, select `email`, `profile`, `openid`.
4. Go to **APIs & Services** &rarr; **Credentials**:
   - Click **Create Credentials** &rarr; **OAuth client ID**.
   - Application type: **Web application**.
   - **Authorized JavaScript origins**:
     - `http://127.0.0.1:8000` (for local dev)
     - `https://your-service-name.onrender.com` (your Render URL)
5. Copy the **Client ID** (e.g. `123456789-abcdef.apps.googleusercontent.com`).

---

## Step 3: Set Up Free Transactional Email (Brevo / Gmail)

GasQ uses an email verification code (6-digit OTP) as a free alternative to paid SMS:

### Option A: Brevo (Recommended, 300 free emails/day)
1. Sign up at [brevo.com](https://www.brevo.com).
2. Go to **Transactional** &rarr; **Settings** &rarr; **SMTP & API**.
3. Note your credentials:
   - Host: `smtp-relay.brevo.com`
   - Port: `587`
   - Username: your Brevo login email
   - Master Password / SMTP Key

### Option B: Gmail App Password
1. In your Google Account, enable **2-Step Verification**.
2. Go to **App Passwords** and generate a 16-character password named `GasQ`.
   - Host: `smtp.gmail.com`
   - Port: `587`
   - Username: `your.email@gmail.com`
   - Password: `your-16-char-app-password`

---

## Step 4: Deploy Backend & Frontend on Render.com

1. Push your repository to GitHub.
2. Sign in to [render.com](https://render.com).
3. Click **New +** &rarr; **Web Service**.
4. Connect your GitHub repository (`GasQ`).
5. Configure the service:
   - **Name**: `gasq-app` (or any preferred name)
   - **Region**: Choose the region closest to your database (e.g. `Ohio (US East)` for AWS `us-east-2`).
   - **Environment**: **Docker** (Render will automatically detect the root `Dockerfile`).
   - **Instance Type**: **Free** ($0/month).
6. Under **Environment Variables**, add the following:

| Key | Value | Description |
| :--- | :--- | :--- |
| `GASQ_ENVIRONMENT` | `production` | Enables production mode |
| `GASQ_DATABASE_URL` | `postgresql://...` | Connection string from Step 1 |
| `GASQ_SECRET_KEY` | *(generate with `openssl rand -hex 32`)* | JWT signing secret |
| `GASQ_CORS_ORIGINS` | `https://gasq-app.onrender.com` | Your public Render URL |
| `GASQ_GOOGLE_CLIENT_ID`| *(from Step 2, optional)* | Google OAuth client ID |
| `GASQ_MAIL_PROVIDER` | `smtp` | Enables email sending |
| `GASQ_SMTP_HOST` | `smtp-relay.brevo.com` | SMTP relay server |
| `GASQ_SMTP_PORT` | `587` | SMTP port |
| `GASQ_SMTP_USERNAME` | *(your SMTP email)* | SMTP authentication user |
| `GASQ_SMTP_PASSWORD` | *(your SMTP password/key)* | SMTP password |
| `GASQ_PHONE_OTP_ENABLED`| `false` | Zero-cost phone collection flag |
| `GASQ_ADMIN_EMAIL` | `admin@gasq.local` | Superadmin initial login |
| `GASQ_ADMIN_PASSWORD` | *(your secure password)* | Superadmin initial password |

7. Click **Create Web Service**.
8. Render will build the container, execute the `entrypoint.sh` script (which automatically runs `alembic upgrade head`), and boot `uvicorn`.

---

## Step 5: Verify Deployment Health

Once the deployment status indicates **Live**, verify the endpoints using your browser or curl:

1. **System Health Check**:
   ```bash
   curl https://your-service.onrender.com/health
   # Expected response: {"status":"ok"}
   ```

2. **Database Readiness Check**:
   ```bash
   curl https://your-service.onrender.com/ready
   # Expected response: {"status":"ready"}
   ```

3. **Public Frontend Pages**:
   - Landing page: `https://your-service.onrender.com/`
   - Customer Portal: `https://your-service.onrender.com/customer.html`
   - Dealer Directory: `https://your-service.onrender.com/dealers.html`
   - Dealer Dashboard: `https://your-service.onrender.com/dealer-dashboard.html`
   - Admin Login: `https://your-service.onrender.com/admin/login`

---

## Step 6: Testing with Docker Compose Locally (Pre-Deployment Validation)

You can validate the full containerized production build locally on your machine with PostgreSQL before cloud deployment:

```powershell
# 1. Build and start containers
docker compose up --build

# 2. In another terminal, check health
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready

# 3. Stop containers when done
docker compose down
```

---

## Post-Deployment Administration

- **Admin Login**: Access `/admin/login` using your configured `GASQ_ADMIN_EMAIL` and `GASQ_ADMIN_PASSWORD`.
- **Dealer Approvals**: Newly registered dealer shops start in `PENDING` status. As admin, call `POST /admin/dealers/{id}/approve` with your admin Bearer token to activate the shop for public customers.
- **Audit Logs**: Query `GET /admin/audit-logs` to inspect all token events, stock reservations, and dealer actions.
