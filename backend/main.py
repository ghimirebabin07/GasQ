import asyncio
import logging
import traceback
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from config import get_settings
from database import Base, SessionLocal, engine
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from models import AdminUser, Customer, Dealer, Token, TokenStatus
from rate_limit import RateLimitMiddleware
from routers import admin, auth, customer, dealer, queue
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("gasq.startup")

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


def run_db_migrations() -> None:
    """Run Alembic migrations programmatically to ensure current schema."""
    try:
        from alembic import command
        from alembic.config import Config

        alembic_ini_path = Path(__file__).resolve().parent / "alembic.ini"
        if alembic_ini_path.exists():
            cfg = Config(str(alembic_ini_path))
            command.upgrade(cfg, "head")
        else:
            logger.warning("alembic.ini not found, falling back to create_all")
            Base.metadata.create_all(bind=engine)
    except Exception:
        logger.error("Alembic migration failed, falling back to create_all:\n%s", traceback.format_exc())
        Base.metadata.create_all(bind=engine)


def seed_database(db: Session) -> None:
    settings = get_settings()
    if settings.admin_email and settings.admin_password:
        from auth import hash_password

        admin_email = settings.admin_email.strip().lower()
        admin_user = db.query(AdminUser).filter(AdminUser.email == admin_email).first()
        if not admin_user:
            db.add(
                AdminUser(
                    email=admin_email,
                    password_hash=hash_password(settings.admin_password),
                    is_active=True,
                )
            )
            db.commit()

    if db.query(Dealer).count() == 0:
        dealers = [
            Dealer(
                name="ABC LPG Dealer",
                address="Kathmandu",
                latitude=27.7172,
                longitude=85.3240,
                phone="9800000001",
                available_cylinders=35,
            ),
            Dealer(
                name="XYZ LPG Dealer",
                address="Lalitpur",
                latitude=27.6588,
                longitude=85.3247,
                phone="9800000002",
                available_cylinders=18,
            ),
            Dealer(
                name="PQR LPG Dealer",
                address="Bhaktapur",
                latitude=27.6710,
                longitude=85.4298,
                phone="9800000003",
                available_cylinders=0,
            ),
        ]
        db.add_all(dealers)
        db.commit()

    if db.query(Customer).count() == 0:
        customers = [
            Customer(name="Sample Customer One", phone="9811111111"),
            Customer(name="Sample Customer Two", phone="9822222222"),
            Customer(name="Sample Customer Three", phone="9833333333"),
        ]
        db.add_all(customers)
        db.commit()

    if db.query(Token).count() == 0:
        dealer = db.query(Dealer).filter(Dealer.name == "ABC LPG Dealer").first()
        customers = db.query(Customer).order_by(Customer.id.asc()).all()
        if dealer and customers:
            for index, sample_customer in enumerate(customers, start=101):
                db.add(
                    Token(
                        dealer_id=dealer.id,
                        customer_id=sample_customer.id,
                        token_number=index,
                        status=TokenStatus.WAITING,
                    )
                )
            db.commit()


def initialize_database() -> None:
    logger.info("Initializing database (environment=%s)", settings.environment)
    if settings.environment != "test":
        logger.info("Running Alembic migrations...")
        run_db_migrations()
        logger.info("Alembic migrations complete.")
    else:
        logger.info("Test environment — creating tables directly.")
        Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        logger.info("Seeding database...")
        seed_database(db)
        logger.info("Database seeding complete.")
    except Exception:
        logger.error("seed_database failed:\n%s", traceback.format_exc())
        raise
    finally:
        db.close()
    logger.info("Database initialization finished.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        initialize_database()
    except Exception:
        logger.error("initialize_database crashed:\n%s", traceback.format_exc())
        raise

    scheduler_task = None
    if settings.environment != "test":
        try:
            from workers.scheduler import background_scheduler_loop

            scheduler_task = asyncio.create_task(background_scheduler_loop(interval_seconds=30))
            logger.info("Background scheduler started.")
        except Exception:
            logger.error("Failed to start background scheduler:\n%s", traceback.format_exc())
            raise

    logger.info("Application startup complete — yielding to uvicorn.")
    try:
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if settings.environment == "production":
            proto = request.headers.get("x-forwarded-proto", "")
            if proto == "http":
                url = request.url.replace(scheme="https")
                return RedirectResponse(url=str(url), status_code=301)

        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://accounts.google.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
            "frame-src https://accounts.google.com; connect-src 'self' https://accounts.google.com;"
        )
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app = FastAPI(
    title="LPG Gas Digital Queue Management System",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(dealer.router)
app.include_router(queue.router)
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def landing_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready():
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
    return {"status": "ready"}


@app.get("/{page_name}.html", include_in_schema=False)
def frontend_page(page_name: str):
    page_path = FRONTEND_DIR / f"{page_name}.html"
    if page_path.exists():
        return FileResponse(page_path)
    return FileResponse(FRONTEND_DIR / "index.html")
