import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

import bcrypt
import jwt
from config import get_settings
from database import get_db
from fastapi import Depends, Header, HTTPException, Request, Response, status
from models.admin_user import AdminUser
from models.customer import Customer
from models.dealer import Dealer
from models.refresh_token import RefreshToken
from sqlalchemy.orm import Session
from time_utils import utc_now

PBKDF2_ITERATIONS = 260_000
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash password with bcrypt using a minimum cost of 12."""
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify password using constant-time comparisons."""
    if not password_hash:
        return False

    # Check for bcrypt format
    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    # Check for legacy PBKDF2 format
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_b64.encode())
            expected_digest = base64.urlsafe_b64decode(digest_b64.encode())
            actual_digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                int(iterations),
            )
            return hmac.compare_digest(actual_digest, expected_digest)
        except (ValueError, TypeError):
            return False

    return False


def create_access_token(
    subject: int | str,
    role: str = "dealer",
    auth_time: int | None = None,
) -> str:
    """
    Generate short-lived access JWT.
    Enforces role-based idle timeouts (15 min admin, 30 min dealer)
    and absolute timeouts (4 hr admin, 8 hr dealer) with random session jti.
    """
    settings = get_settings()
    now_ts = int(time.time())

    # Role-specific idle timeout (access token lifetime)
    if role == "admin":
        ttl = settings.admin_idle_timeout_seconds
        abs_ttl = settings.admin_absolute_timeout_seconds
    elif role == "dealer":
        ttl = settings.dealer_idle_timeout_seconds
        abs_ttl = settings.dealer_absolute_timeout_seconds
    else:
        ttl = settings.access_token_ttl_seconds or settings.token_ttl_seconds
        abs_ttl = settings.token_ttl_seconds

    origin_auth_time = int(auth_time or now_ts)
    abs_exp = origin_auth_time + abs_ttl

    payload = {
        "sub": str(subject),
        "role": role,
        "iat": now_ts,
        "exp": now_ts + ttl,
        "auth_time": origin_auth_time,
        "abs_exp": abs_exp,
        "jti": secrets.token_hex(24),  # Session ID regeneration to prevent fixation
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> tuple[str, str]:
    """
    Decode and validate access token.
    Enforces idle signature expiration and hard absolute timeout limit.
    """
    settings = get_settings()

    # Try PyJWT standard decoding first
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        role = payload.get("role", "")
        subject = payload.get("sub", "")
        if not role or not subject:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

        # Check absolute session expiry
        abs_exp = payload.get("abs_exp")
        if abs_exp and int(time.time()) > int(abs_exp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Absolute timeout reached.",
            )

        return role, subject
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    except jwt.PyJWTError:
        pass

    # Fallback to legacy HMAC signed token format
    try:
        role, encoded_subject, expires_at, nonce, signature = token.split(".", 4)
        raw_payload = f"{role}.{encoded_subject}.{expires_at}.{nonce}"
        expected_signature = hmac.new(
            settings.secret_key.encode(),
            raw_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        expires_at_value = int(expires_at)
        padded_subject = encoded_subject + "=" * (-len(encoded_subject) % 4)
        subject = base64.urlsafe_b64decode(padded_subject.encode("ascii")).decode("utf-8")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if expires_at_value < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return role, subject


def create_refresh_token(
    db: Session,
    user_type: str,
    user_id: int,
    created_at: datetime | None = None,
) -> str:
    """Create a high-entropy random refresh token stored hashed in database."""
    settings = get_settings()
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    issued_at = created_at or utc_now()
    expires_at = issued_at + timedelta(days=settings.refresh_token_ttl_days)

    refresh_record = RefreshToken(
        user_type=user_type,
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=issued_at,
    )
    db.add(refresh_record)
    db.commit()
    return raw_token


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[str, str, str, int]:
    """
    Rotate refresh token upon use.
    Enforces REUSE DETECTION: if a revoked token is presented, all active sessions
    for that account are revoked immediately as a security breach countermeasure.
    Enforces absolute timeout limits based on session creation time.
    """
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = utc_now()
    settings = get_settings()

    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .first()
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # REUSE DETECTION: Token was already revoked!
    if record.revoked_at is not None:
        db.query(RefreshToken).filter(
            RefreshToken.user_type == record.user_type,
            RefreshToken.user_id == record.user_id,
            RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": now})
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions for this account have been revoked.",
        )

    # Absolute session lifetime check
    if record.user_type == "admin":
        max_lifetime = timedelta(seconds=settings.admin_absolute_timeout_seconds)
    elif record.user_type == "dealer":
        max_lifetime = timedelta(seconds=settings.dealer_absolute_timeout_seconds)
    else:
        max_lifetime = timedelta(days=settings.refresh_token_ttl_days)

    if now - record.created_at > max_lifetime:
        record.revoked_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session absolute timeout reached. Please log in again.",
        )

    if record.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Revoke old token
    record.revoked_at = now
    db.flush()

    # Issue new token pair propagating session auth_time
    auth_time = int(record.created_at.timestamp())
    new_access_token = create_access_token(subject=record.user_id, role=record.user_type, auth_time=auth_time)
    new_refresh_token = create_refresh_token(
        db,
        user_type=record.user_type,
        user_id=record.user_id,
        created_at=record.created_at,
    )
    return new_access_token, new_refresh_token, record.user_type, record.user_id


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """Invalidate a refresh token on server upon logout."""
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .first()
    )
    if record:
        record.revoked_at = utc_now()
        db.commit()


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    role: str = "admin",
) -> str:
    """
    Configure HttpOnly, Secure, SameSite=Strict cookies on HTTP response.
    Returns generated CSRF token.
    """
    settings = get_settings()
    is_secure = settings.cookie_secure or (settings.environment == "production")

    if role == "admin":
        access_max_age = settings.admin_idle_timeout_seconds
        refresh_max_age = settings.admin_absolute_timeout_seconds
    elif role == "dealer":
        access_max_age = settings.dealer_idle_timeout_seconds
        refresh_max_age = settings.dealer_absolute_timeout_seconds
    else:
        access_max_age = settings.access_token_ttl_seconds
        refresh_max_age = settings.refresh_token_ttl_days * 86400

    # Access Token Cookie (HttpOnly)
    response.set_cookie(
        key=f"gasq_{role}_access",
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        path="/",
    )

    # Refresh Token Cookie (HttpOnly)
    response.set_cookie(
        key=f"gasq_{role}_refresh",
        value=refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        path="/",
    )

    # CSRF Token Cookie (Readable by JS for Double Submit Cookie verification)
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key="gasq_csrf",
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=is_secure,
        samesite="strict",
        path="/",
    )

    return csrf_token


def clear_auth_cookies(response: Response, role: str | None = None) -> None:
    """Delete all session and CSRF cookies on logout."""
    roles = [role] if role else ["admin", "dealer", "customer"]
    for r in roles:
        response.delete_cookie(key=f"gasq_{r}_access", path="/")
        response.delete_cookie(key=f"gasq_{r}_refresh", path="/")
    response.delete_cookie(key="gasq_csrf", path="/")


def _extract_token_and_verify_csrf(
    request: Request,
    authorization: str | None,
    cookie_name: str,
) -> str | None:
    """
    Extract token from Authorization header or HttpOnly cookie.
    Enforces CSRF token check if token was supplied via cookie on state-changing requests.
    """
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()

    cookie_token = request.cookies.get(cookie_name)
    if cookie_token:
        # Check CSRF for state-changing HTTP methods
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf_cookie = request.cookies.get("gasq_csrf")
            csrf_header = request.headers.get("x-csrf-token")
            if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF token missing or invalid",
                )
        return cookie_token

    return None


def get_current_dealer(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Dealer:
    """Dependency returning authenticated Dealer (supports Bearer header and HttpOnly cookie)."""
    token = _extract_token_and_verify_csrf(request, authorization, "gasq_dealer_access")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dealer login required",
        )

    try:
        role, dealer_id = decode_access_token(token)
        dealer_id_value = int(dealer_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if role != "dealer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dealer role required")

    dealer = db.get(Dealer, dealer_id_value)
    if not dealer or not dealer.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Dealer not found")
    return dealer


def get_current_admin(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Dependency returning authenticated AdminUser with server-side role check."""
    token = _extract_token_and_verify_csrf(request, authorization, "gasq_admin_access")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin login required",
        )

    role, subject = decode_access_token(token)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    # Subject can be admin email or ID
    admin_user = None
    if subject.isdigit():
        admin_user = db.get(AdminUser, int(subject))
    if not admin_user:
        admin_user = db.query(AdminUser).filter(AdminUser.email == subject).first()

    if not admin_user or not admin_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin account not found or disabled")
    return admin_user


def get_current_customer(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Customer:
    """Dependency returning authenticated Customer."""
    token = _extract_token_and_verify_csrf(request, authorization, "gasq_customer_access")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer login required",
        )

    role, customer_id = decode_access_token(token)
    if role != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer role required")
    try:
        customer_id_value = int(customer_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    customer = db.get(Customer, customer_id_value)
    if not customer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Customer not found")
    return customer
