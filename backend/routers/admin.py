from auth import (
    create_access_token,
    create_refresh_token,
    get_current_admin,
    set_auth_cookies,
    verify_password,
)
from database import get_db
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from models.admin_user import AdminUser
from models.audit_log import AuditLog
from models.dealer import Dealer
from models.notification import Notification
from schemas.admin import (
    Admin2FASetupResponse,
    AdminDealerRead,
    AdminLogin,
    AdminLoginResponse,
    AdminNotificationRead,
    AdminReauthRequest,
)
from schemas.audit import AuditLogRead
from services.audit_service import record_audit_log
from services.login_security_service import (
    check_account_lockout,
    record_failed_login,
    record_successful_login,
)
from services.totp_service import (
    build_totp_provisioning_uri,
    generate_totp_secret,
    verify_totp,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("/login", response_model=AdminLoginResponse)
def login_admin(
    credentials: AdminLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email = credentials.email.strip().lower()
    client_ip = _get_client_ip(request)

    admin_user = db.query(AdminUser).filter(AdminUser.email == email).first()

    # 1. Enforce brute-force protection and account lockout
    check_account_lockout(email, client_ip, admin_user)

    # 2. Generic constant-time check: Do not leak whether user exists or password was wrong
    if not admin_user or not admin_user.is_active or not verify_password(credentials.password, admin_user.password_hash):
        record_failed_login(db, email, client_ip, admin_user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # 3. Two-Factor Authentication (TOTP) verification if enabled
    if admin_user.totp_secret:
        if not credentials.totp_code:
            # Inform client that 2FA code is required
            return AdminLoginResponse(
                access_token="",
                refresh_token=None,
                requires_2fa=True,
            )

        if not verify_totp(admin_user.totp_secret, credentials.totp_code):
            record_failed_login(db, email, client_ip, admin_user)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    # 4. Successful login: reset failed counters and write audit log
    record_successful_login(db, email, client_ip, admin_user)

    access_token = create_access_token(admin_user.email, role="admin")
    refresh_token = create_refresh_token(db, user_type="admin", user_id=admin_user.id)

    # Set secure HttpOnly cookies + CSRF cookie on response
    csrf_token = set_auth_cookies(response, access_token, refresh_token, role="admin")

    return AdminLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        csrf_token=csrf_token,
        requires_2fa=False,
    )


@router.post("/reauth")
def reauth_admin(
    payload: AdminReauthRequest,
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Verify admin password prior to performing high-risk administrative operations."""
    if not verify_password(payload.password, current_admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid confirmation password")
    return {"status": "ok", "message": "Admin re-authentication confirmed"}


@router.post("/2fa/setup", response_model=Admin2FASetupResponse)
def setup_2fa(
    current_admin: AdminUser = Depends(get_current_admin),
):
    """Generate a new standard RFC 6238 TOTP secret and provisioning URI for Google Authenticator."""
    secret = generate_totp_secret()
    uri = build_totp_provisioning_uri(secret, account_name=current_admin.email)
    return Admin2FASetupResponse(secret=secret, provisioning_uri=uri)


@router.post("/2fa/enable")
def enable_2fa(
    secret: str,
    totp_code: str,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Verify initial TOTP code and enable 2FA on the admin account."""
    if not verify_totp(secret, totp_code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code. Please scan the QR code and try again.")

    current_admin.totp_secret = secret
    record_audit_log(
        db,
        actor_type="admin",
        actor_id=current_admin.email,
        action="ADMIN_2FA_ENABLED",
        entity_type="admin",
        entity_id=current_admin.email,
    )
    db.commit()
    return {"status": "ok", "message": "Two-factor authentication enabled successfully"}


@router.post("/2fa/disable")
def disable_2fa(
    payload: AdminReauthRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Disable 2FA after verifying the admin password."""
    if not verify_password(payload.password, current_admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid confirmation password")

    current_admin.totp_secret = None
    record_audit_log(
        db,
        actor_type="admin",
        actor_id=current_admin.email,
        action="ADMIN_2FA_DISABLED",
        entity_type="admin",
        entity_id=current_admin.email,
    )
    db.commit()
    return {"status": "ok", "message": "Two-factor authentication disabled"}


@router.get("/dealers", response_model=list[AdminDealerRead])
def list_admin_dealers(
    status_filter: str | None = None,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Dealer).order_by(Dealer.created_at.desc(), Dealer.id.desc())
    if status_filter:
        query = query.filter(Dealer.status == status_filter.upper())
    return query.all()


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = 100,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    safe_limit = min(max(limit, 1), 500)
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(safe_limit)
        .all()
    )


@router.get("/notifications", response_model=list[AdminNotificationRead])
def list_notifications(
    limit: int = 100,
    current_admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    safe_limit = min(max(limit, 1), 500)
    return (
        db.query(Notification)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(safe_limit)
        .all()
    )


@router.post("/dealers/{dealer_id}/approve", response_model=AdminDealerRead)
def approve_dealer(
    dealer_id: int,
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    x_admin_password: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # Sensitive action password verification if supplied
    if x_admin_password and not verify_password(x_admin_password, current_admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid confirmation password")

    dealer = db.get(Dealer, dealer_id)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
    old_value = {"status": dealer.status, "is_active": dealer.is_active}
    dealer.status = "APPROVED"
    dealer.is_active = True
    record_audit_log(
        db,
        actor_type="admin",
        actor_id=current_admin.email,
        action="DEALER_APPROVED",
        entity_type="dealer",
        entity_id=dealer.id,
        old_value=old_value,
        new_value={
            "status": dealer.status,
            "is_active": dealer.is_active,
            "client_ip": _get_client_ip(request),
        },
    )
    db.commit()
    db.refresh(dealer)
    return dealer


@router.post("/dealers/{dealer_id}/suspend", response_model=AdminDealerRead)
def suspend_dealer(
    dealer_id: int,
    request: Request,
    current_admin: AdminUser = Depends(get_current_admin),
    x_admin_password: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # Sensitive action password verification if supplied
    if x_admin_password and not verify_password(x_admin_password, current_admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid confirmation password")

    dealer = db.get(Dealer, dealer_id)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
    old_value = {"status": dealer.status, "is_active": dealer.is_active}
    dealer.status = "SUSPENDED"
    dealer.is_active = False
    record_audit_log(
        db,
        actor_type="admin",
        actor_id=current_admin.email,
        action="DEALER_SUSPENDED",
        entity_type="dealer",
        entity_id=dealer.id,
        old_value=old_value,
        new_value={
            "status": dealer.status,
            "is_active": dealer.is_active,
            "client_ip": _get_client_ip(request),
        },
    )
    db.commit()
    db.refresh(dealer)
    return dealer
