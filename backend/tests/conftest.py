import importlib
import sys

import pytest
from fastapi.testclient import TestClient

PROJECT_MODULES = [
    "main",
    "database",
    "auth",
    "config",
    "rate_limit",
    "models",
    "models.admin_user",
    "models.audit_log",
    "models.customer",
    "models.dealer",
    "models.email_otp",
    "models.notification",
    "models.refresh_token",
    "models.token",
    "routers",
    "routers.admin",
    "routers.auth",
    "routers.customer",
    "routers.dealer",
    "routers.queue",
    "schemas",
    "schemas.admin",
    "schemas.audit",
    "schemas.auth",
    "schemas.customer",
    "schemas.dealer",
    "schemas.notification",
    "schemas.token",
    "services",
    "services.audit_service",
    "services.google_auth_service",
    "services.mail_service",
    "services.notification_service",
    "services.otp_service",
    "services.queue_service",
    "services.sms_service",
    "workers",
    "workers.scheduler",
    "time_utils",
]


def clear_project_modules():
    for module_name in PROJECT_MODULES:
        sys.modules.pop(module_name, None)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'test_gasq.db').as_posix()}"
    monkeypatch.setenv("GASQ_ENVIRONMENT", "test")
    monkeypatch.setenv("GASQ_DATABASE_URL", database_url)
    monkeypatch.setenv("GASQ_SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long!")
    monkeypatch.setenv("GASQ_CORS_ORIGINS", "http://testserver")
    monkeypatch.setenv("GASQ_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("GASQ_ADMIN_PASSWORD", "Admin12345")
    monkeypatch.setenv("GASQ_MAIL_PROVIDER", "console")
    try:
        from services.login_security_service import reset_login_security_state

        reset_login_security_state()
    except Exception:
        pass

    main = importlib.import_module("main")
    with TestClient(main.app) as test_client:
        yield test_client

    try:
        from services.login_security_service import reset_login_security_state

        reset_login_security_state()
    except Exception:
        pass
    clear_project_modules()
