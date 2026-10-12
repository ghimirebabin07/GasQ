from auth import (
    clear_auth_cookies,
    revoke_refresh_token,
    rotate_refresh_token,
    set_auth_cookies,
)
from database import get_db
from fastapi import APIRouter, Depends, Request, Response
from models.admin_user import AdminUser
from models.customer import Customer
from models.dealer import Dealer
from schemas.auth import RefreshTokenRequest, TokenResponse
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(
    refresh_data: RefreshTokenRequest | None = None,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
):
    # Extract token from payload or HttpOnly cookie
    raw_token = None
    if refresh_data and refresh_data.refresh_token:
        raw_token = refresh_data.refresh_token
    elif request:
        raw_token = (
            request.cookies.get("gasq_admin_refresh")
            or request.cookies.get("gasq_dealer_refresh")
            or request.cookies.get("gasq_customer_refresh")
        )

    if not raw_token:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )

    new_access_token, new_refresh_token, user_type, user_id = rotate_refresh_token(
        db, raw_token
    )

    user_info = {"id": user_id, "role": user_type}
    if user_type == "customer":
        customer = db.get(Customer, user_id)
        if customer:
            user_info["name"] = customer.name
            user_info["phone"] = customer.phone
            user_info["email"] = customer.email
    elif user_type == "dealer":
        dealer = db.get(Dealer, user_id)
        if dealer:
            user_info["name"] = dealer.name
            user_info["username"] = dealer.username
            user_info["email"] = dealer.email
            user_info["status"] = dealer.status
    elif user_type == "admin":
        admin_user = db.get(AdminUser, user_id)
        if admin_user:
            user_info["email"] = admin_user.email

    # Set rotated cookies on response
    if response:
        set_auth_cookies(response, new_access_token, new_refresh_token, role=user_type)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "user": user_info,
    }


@router.post("/logout")
def logout(
    logout_data: RefreshTokenRequest | None = None,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
):
    raw_token = None
    if logout_data and logout_data.refresh_token:
        raw_token = logout_data.refresh_token
    elif request:
        raw_token = (
            request.cookies.get("gasq_admin_refresh")
            or request.cookies.get("gasq_dealer_refresh")
            or request.cookies.get("gasq_customer_refresh")
        )

    if raw_token:
        revoke_refresh_token(db, raw_token)

    if response:
        clear_auth_cookies(response)

    return {"message": "Logged out successfully"}


@router.get("/config")
def auth_config():
    from config import get_settings

    settings = get_settings()
    return {
        "google_client_id": settings.google_client_id,
        "phone_otp_enabled": settings.phone_otp_enabled,
    }
