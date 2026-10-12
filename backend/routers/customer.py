import asyncio
import json

from auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_current_customer,
    hash_password,
    verify_password,
)
from database import get_db
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from models.customer import Customer
from models.notification import Notification
from schemas.auth import EmailOtpSendRequest, EmailOtpVerifyRequest, GoogleAuthRequest
from schemas.customer import (
    CustomerCreate,
    CustomerLogin,
    CustomerLoginResponse,
    CustomerPhoneUpdate,
    CustomerRead,
)
from schemas.notification import NotificationRead
from schemas.token import TokenRead
from services import queue_service
from services.google_auth_service import get_google_verifier
from services.notification_service import notification_bus
from services.otp_service import send_email_otp, verify_email_otp
from sqlalchemy.orm import Session
from time_utils import utc_now

router = APIRouter(tags=["customers"])


def customer_login_response(customer: Customer, db: Session) -> CustomerLoginResponse:
    access_token = create_access_token(customer.id, role="customer")
    refresh_token = create_refresh_token(db, user_type="customer", user_id=customer.id)
    return CustomerLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        customer=customer,
    )


@router.post("/customer/register", response_model=CustomerLoginResponse, status_code=status.HTTP_201_CREATED)
def create_customer(customer_data: CustomerCreate, db: Session = Depends(get_db)):
    phone = customer_data.phone.strip()
    existing_customer = db.query(Customer).filter(Customer.phone == phone).first()
    if existing_customer:
        if existing_customer.password_hash:
            raise HTTPException(status_code=400, detail="Phone number is already registered")
        existing_customer.name = customer_data.name.strip()
        existing_customer.password_hash = hash_password(customer_data.password)
        db.commit()
        db.refresh(existing_customer)
        return customer_login_response(existing_customer, db)

    customer = Customer(
        name=customer_data.name.strip(),
        phone=phone,
        password_hash=hash_password(customer_data.password),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer_login_response(customer, db)


@router.post("/customers", response_model=CustomerLoginResponse, status_code=status.HTTP_201_CREATED)
def create_customer_compat(customer_data: CustomerCreate, db: Session = Depends(get_db)):
    return create_customer(customer_data, db)


@router.post("/customer/login", response_model=CustomerLoginResponse)
def login_customer(credentials: CustomerLogin, db: Session = Depends(get_db)):
    phone = credentials.phone.strip()
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer or not verify_password(credentials.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid customer phone or password")
    return customer_login_response(customer, db)


@router.post("/customer/auth/google", response_model=CustomerLoginResponse)
def google_auth_customer(
    request: GoogleAuthRequest,
    db: Session = Depends(get_db),
    verifier=Depends(get_google_verifier),
):
    id_info = verifier(request.id_token)
    email = id_info.get("email", "").strip().lower()
    google_id = id_info.get("sub", "")
    name = id_info.get("name") or email.split("@")[0] or "Customer"

    customer = None
    if google_id:
        customer = db.query(Customer).filter(Customer.google_id == google_id).first()
    if not customer and email:
        customer = db.query(Customer).filter(Customer.email == email).first()

    if customer:
        if not customer.google_id:
            customer.google_id = google_id
        if not customer.email and email:
            customer.email = email
        db.commit()
        db.refresh(customer)
    else:
        customer = Customer(
            name=name,
            email=email,
            google_id=google_id,
            is_phone_verified=False,
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)

    return customer_login_response(customer, db)


@router.post("/customer/auth/otp/send")
def request_customer_otp(request: EmailOtpSendRequest, db: Session = Depends(get_db)):
    send_email_otp(db, str(request.email))
    return {
        "message": "Verification code sent to your email",
        "email": str(request.email),
    }


@router.post("/customer/auth/otp/verify", response_model=CustomerLoginResponse)
def verify_customer_otp(request: EmailOtpVerifyRequest, db: Session = Depends(get_db)):
    email = str(request.email).strip().lower()
    verify_email_otp(db, email, request.code)

    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        customer = Customer(
            name=email.split("@")[0].capitalize(),
            email=email,
            is_phone_verified=False,
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)

    return customer_login_response(customer, db)


@router.put("/customer/phone", response_model=CustomerRead)
def update_customer_phone(
    update_data: CustomerPhoneUpdate,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    phone = update_data.phone.strip()
    existing = db.query(Customer).filter(Customer.phone == phone, Customer.id != current_customer.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This phone number is already registered with another customer",
        )

    current_customer.phone = phone
    current_customer.is_phone_verified = False  # Stored as unverified until SMS provider is enabled
    db.commit()
    db.refresh(current_customer)
    return current_customer


@router.get("/customer/me", response_model=CustomerRead)
def get_customer_profile(current_customer: Customer = Depends(get_current_customer)):
    return current_customer


@router.get("/customer/tokens", response_model=list[TokenRead])
def list_customer_tokens(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    from models.token import Token

    return (
        db.query(Token)
        .filter(Token.customer_id == current_customer.id)
        .order_by(Token.created_at.desc(), Token.id.desc())
        .limit(50)
        .all()
    )


@router.get("/customer/tokens/active")
def get_customer_active_token(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    from routers.queue import build_queue_status

    token = queue_service.get_active_token_for_customer(db, current_customer.id)
    if not token:
        return {"has_active_token": False, "token": None}
    status = build_queue_status(db, token.id)
    return {"has_active_token": True, "token": status}


@router.get("/customer/notifications", response_model=list[NotificationRead])
def list_customer_notifications(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    return (
        db.query(Notification)
        .filter(Notification.user_type == "customer", Notification.user_id == str(current_customer.id))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
        .all()
    )


@router.get("/customer/notifications/unread-count")
def get_unread_notification_count(
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    count = (
        db.query(Notification)
        .filter(
            Notification.user_type == "customer",
            Notification.user_id == str(current_customer.id),
            Notification.read_at.is_(None),
        )
        .count()
    )
    return {"unread_count": count}


@router.post("/customer/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_type == "customer",
            Notification.user_id == str(current_customer.id),
        )
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notification.read_at:
        notification.read_at = utc_now()
        db.commit()
    return {"status": "ok", "read_at": notification.read_at}


@router.get("/customer/notifications/stream")
async def stream_customer_notifications(
    token: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    raw_token = token
    if not raw_token and authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()

    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required")

    role, customer_id = decode_access_token(raw_token)
    if role != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer role required")

    customer = db.get(Customer, int(customer_id))
    if not customer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Customer not found")

    user_id_str = str(customer.id)
    queue = notification_bus.subscribe("customer", user_id_str)

    async def event_generator():
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: notification\ndata: {json.dumps(payload)}\n\n"
                except TimeoutError:
                    # Keep-alive heartbeat ping
                    yield "event: ping\ndata: {}\n\n"
        finally:
            notification_bus.unsubscribe("customer", user_id_str, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
