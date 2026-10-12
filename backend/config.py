from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{(BASE_DIR / 'backend' / 'lpg_queue.db').as_posix()}"


class Settings(BaseSettings):
    environment: str = Field(default="development", alias="GASQ_ENVIRONMENT")
    database_url: str = Field(default=DEFAULT_DATABASE_URL, alias="GASQ_DATABASE_URL")
    secret_key: str = Field(default_factory=lambda: token_urlsafe(48), alias="GASQ_SECRET_KEY")
    token_ttl_seconds: int = Field(default=60 * 60 * 12, alias="GASQ_TOKEN_TTL_SECONDS")
    access_token_ttl_seconds: int = Field(default=900, alias="GASQ_ACCESS_TOKEN_TTL_SECONDS")
    refresh_token_ttl_days: int = Field(default=7, alias="GASQ_REFRESH_TOKEN_TTL_DAYS")
    cors_origins: str = Field(
        default="http://127.0.0.1:8000,http://127.0.0.1:8001",
        alias="GASQ_CORS_ORIGINS",
    )
    google_client_id: str = Field(default="", alias="GASQ_GOOGLE_CLIENT_ID")
    mail_provider: str = Field(default="console", alias="GASQ_MAIL_PROVIDER")
    smtp_host: str = Field(default="", alias="GASQ_SMTP_HOST")
    smtp_port: int = Field(default=587, alias="GASQ_SMTP_PORT")
    smtp_username: str = Field(default="", alias="GASQ_SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="GASQ_SMTP_PASSWORD")
    phone_otp_enabled: bool = Field(default=False, alias="GASQ_PHONE_OTP_ENABLED")
    admin_email: str = Field(default="", alias="GASQ_ADMIN_EMAIL")
    admin_password: str = Field(default="", alias="GASQ_ADMIN_PASSWORD")
    rate_limit_window_seconds: int = Field(default=60, alias="GASQ_RATE_LIMIT_WINDOW_SECONDS")
    rate_limit_requests: int = Field(default=600, alias="GASQ_RATE_LIMIT_REQUESTS")
    auth_rate_limit_requests: int = Field(default=60, alias="GASQ_AUTH_RATE_LIMIT_REQUESTS")
    queue_rate_limit_requests: int = Field(default=120, alias="GASQ_QUEUE_RATE_LIMIT_REQUESTS")
    admin_idle_timeout_seconds: int = Field(default=900, alias="GASQ_ADMIN_IDLE_TIMEOUT_SECONDS")
    admin_absolute_timeout_seconds: int = Field(default=14400, alias="GASQ_ADMIN_ABSOLUTE_TIMEOUT_SECONDS")
    dealer_idle_timeout_seconds: int = Field(default=1800, alias="GASQ_DEALER_IDLE_TIMEOUT_SECONDS")
    dealer_absolute_timeout_seconds: int = Field(default=28800, alias="GASQ_DEALER_ABSOLUTE_TIMEOUT_SECONDS")
    cookie_secure: bool = Field(default=False, alias="GASQ_COOKIE_SECURE")
    admin_totp_required: bool = Field(default=False, alias="GASQ_ADMIN_TOTP_REQUIRED")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
