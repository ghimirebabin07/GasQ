"""
GasQ Login Security Service.
Enforces brute-force defense, account lockouts, common password checks,
and security audit logging for authentication workflows.
"""

import threading
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from models.admin_user import AdminUser
from sqlalchemy.orm import Session
from time_utils import utc_now

from services.audit_service import record_audit_log

# Lockout policy constants
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
WINDOW_MINUTES = 15

# Common weak passwords list to reject
COMMON_PASSWORDS = {
    "password",
    "password123",
    "1234567890",
    "12345678",
    "123456789",
    "admin12345",
    "admin123",
    "administrator",
    "qwertyuiop",
    "letmein123",
    "welcome123",
    "iloveyou123",
    "gasq12345",
    "dealer12345",
}

_lock = threading.Lock()
# In-memory attempt tracking: (key) -> list of timestamp floats
_failed_attempts: dict[str, list[datetime]] = defaultdict(list)
_locked_until: dict[str, datetime] = {}


def reset_login_security_state() -> None:
    """Reset all in-memory lockout and failed attempt tracking (used for tests and admin unlock)."""
    with _lock:
        _failed_attempts.clear()
        _locked_until.clear()


def is_weak_or_common_password(password: str) -> tuple[bool, str | None]:
    """Validate password strength and blacklist common passwords."""
    if len(password) < 10:
        return True, "Password must be at least 10 characters long"
    if password.strip().lower() in COMMON_PASSWORDS:
        return True, "Password is too common and easily guessable"
    return False, None


def check_account_lockout(email: str, client_ip: str, admin_user: AdminUser | None = None) -> None:
    """Check if the account or IP is currently locked out."""
    now = utc_now()
    key_account = f"acc:{email.lower()}"
    key_ip = f"ip:{client_ip}"

    # 1. Check in-memory lockout
    with _lock:
        for k in (key_account, key_ip):
            lock_time = _locked_until.get(k)
            if lock_time and lock_time > now:
                remaining_secs = int((lock_time - now).total_seconds())
                remaining_mins = max(1, remaining_secs // 60)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many failed login attempts. Account temporarily locked for {remaining_mins} minutes.",
                )

    # 2. Check DB-persisted lockout
    if admin_user and admin_user.locked_until and admin_user.locked_until > now:
        remaining_secs = int((admin_user.locked_until - now).total_seconds())
        remaining_mins = max(1, remaining_secs // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Account temporarily locked for {remaining_mins} minutes.",
        )


def record_failed_login(
    db: Session,
    email: str,
    client_ip: str,
    admin_user: AdminUser | None = None,
) -> None:
    """Record a failed login attempt, enforce lockout threshold, and write audit log."""
    now = utc_now()
    cutoff = now - timedelta(minutes=WINDOW_MINUTES)
    key_account = f"acc:{email.lower()}"
    key_ip = f"ip:{client_ip}"

    locked = False
    with _lock:
        # Prune older entries
        _failed_attempts[key_account] = [t for t in _failed_attempts[key_account] if t > cutoff]
        _failed_attempts[key_ip] = [t for t in _failed_attempts[key_ip] if t > cutoff]

        _failed_attempts[key_account].append(now)
        _failed_attempts[key_ip].append(now)

        acc_count = len(_failed_attempts[key_account])
        ip_count = len(_failed_attempts[key_ip])

        if acc_count >= MAX_FAILED_ATTEMPTS or ip_count >= MAX_FAILED_ATTEMPTS:
            lock_expiry = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            _locked_until[key_account] = lock_expiry
            _locked_until[key_ip] = lock_expiry
            locked = True

    # Update DB entity if admin_user exists
    if admin_user:
        admin_user.failed_login_attempts = (admin_user.failed_login_attempts or 0) + 1
        if locked:
            admin_user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        db.commit()

    # Record security audit log
    action = "ADMIN_LOGIN_LOCKED" if locked else "ADMIN_LOGIN_FAILED"
    record_audit_log(
        db,
        actor_type="system",
        actor_id=client_ip,
        action=action,
        entity_type="admin",
        entity_id=email,
        new_value={
            "client_ip": client_ip,
            "account": email,
            "locked": locked,
            "timestamp": now.isoformat(),
        },
    )
    db.commit()

    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Account temporarily locked for {LOCKOUT_DURATION_MINUTES} minutes.",
        )


def record_successful_login(
    db: Session,
    email: str,
    client_ip: str,
    admin_user: AdminUser | None = None,
) -> None:
    """Reset failed login attempts on successful authentication and record audit log."""
    now = utc_now()
    key_account = f"acc:{email.lower()}"
    key_ip = f"ip:{client_ip}"

    with _lock:
        _failed_attempts.pop(key_account, None)
        _failed_attempts.pop(key_ip, None)
        _locked_until.pop(key_account, None)
        _locked_until.pop(key_ip, None)

    if admin_user:
        admin_user.failed_login_attempts = 0
        admin_user.locked_until = None
        db.commit()

    record_audit_log(
        db,
        actor_type="admin",
        actor_id=email,
        action="ADMIN_LOGIN_SUCCESS",
        entity_type="admin",
        entity_id=email,
        new_value={
            "client_ip": client_ip,
            "account": email,
            "timestamp": now.isoformat(),
        },
    )
    db.commit()
