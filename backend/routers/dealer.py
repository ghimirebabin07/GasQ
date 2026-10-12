from auth import (
    create_access_token,
    create_refresh_token,
    get_current_dealer,
    hash_password,
    verify_password,
)
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from models.dealer import Dealer
from models.token import Token, TokenStatus
from schemas.auth import GoogleAuthRequest
from schemas.dealer import (
    DealerCreate,
    DealerCredentials,
    DealerLoginResponse,
    DealerPrivateRead,
    DealerRead,
    DealerUpdate,
    StockUpdate,
)
from schemas.token import DealerDashboard, QueueItem, TokenRead
from services import queue_service
from services.google_auth_service import get_google_verifier
from sqlalchemy import func
from sqlalchemy.orm import Session
from time_utils import utc_now

router = APIRouter(tags=["dealers"])


def require_approved_dealer(dealer: Dealer) -> None:
    if dealer.status != "APPROVED":
        raise HTTPException(status_code=403, detail="Dealer is not approved yet")


def dealer_to_response(db: Session, dealer: Dealer) -> DealerRead:
    return DealerRead(
        id=dealer.id,
        name=dealer.name,
        address=dealer.address,
        latitude=dealer.latitude,
        longitude=dealer.longitude,
        phone=dealer.phone,
        available_cylinders=dealer.available_cylinders,
        status=dealer.status,
        is_active=dealer.is_active,
        created_at=dealer.created_at,
        people_waiting=queue_service.get_waiting_count(db, dealer.id),
        current_serving_token=queue_service.get_current_serving_number(db, dealer.id),
        stock_message=queue_service.build_stock_message(dealer),
    )


def dealer_to_private_response(db: Session, dealer: Dealer) -> DealerPrivateRead:
    public_response = dealer_to_response(db, dealer).model_dump()
    return DealerPrivateRead(**public_response, username=dealer.username, email=dealer.email)


def build_dashboard(db: Session, dealer: Dealer) -> DealerDashboard:
    current_called = queue_service.get_current_called_token(db, dealer.id)
    today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    sold_today = (
        db.query(func.count(Token.id))
        .filter(
            Token.dealer_id == dealer.id,
            Token.status.in_([TokenStatus.SERVED, TokenStatus.COMPLETED]),
            Token.served_at >= today_start,
        )
        .scalar()
        or 0
    )
    queue = [
        QueueItem(
            id=token.id,
            token_number=token.token_number,
            status=token.status,
            customer_name=token.customer.name,
            customer_phone=token.customer.phone,
            created_at=token.created_at,
            called_at=token.called_at,
        )
        for token in queue_service.get_queue_items(db, dealer.id)
    ]
    return DealerDashboard(
        dealer_id=dealer.id,
        dealer_name=dealer.name,
        available_cylinders=dealer.available_cylinders,
        current_serving_token=current_called.token_number if current_called else None,
        current_called_token_id=current_called.id if current_called else None,
        waiting_count=queue_service.get_waiting_count(db, dealer.id),
        cylinders_sold_today=sold_today,
        queue=queue,
    )


@router.get("/dealers", response_model=list[DealerRead])
def list_dealers(db: Session = Depends(get_db)):
    dealers = (
        db.query(Dealer)
        .filter(Dealer.is_active.is_(True), Dealer.status == "APPROVED")
        .order_by(Dealer.id.asc())
        .all()
    )
    return [dealer_to_response(db, dealer) for dealer in dealers]


@router.get("/dealers/{dealer_id}", response_model=DealerRead)
def get_dealer(dealer_id: int, db: Session = Depends(get_db)):
    dealer = queue_service.get_dealer_or_404(db, dealer_id)
    if not dealer.is_active or dealer.status != "APPROVED":
        raise HTTPException(status_code=404, detail="Dealer not found")
    return dealer_to_response(db, dealer)


@router.post("/dealer/register", response_model=DealerLoginResponse, status_code=status.HTTP_201_CREATED)
def register_dealer(dealer_data: DealerCreate, db: Session = Depends(get_db)):
    username = dealer_data.username.strip().lower()
    email = dealer_data.email.strip().lower()
    existing_dealer = (
        db.query(Dealer)
        .filter((Dealer.username == username) | (Dealer.email == email))
        .first()
    )
    if existing_dealer:
        raise HTTPException(status_code=400, detail="Dealer ID or email is already registered")

    dealer = Dealer(
        name=dealer_data.name.strip(),
        username=username,
        email=email,
        password_hash=hash_password(dealer_data.password),
        address=dealer_data.address.strip(),
        latitude=dealer_data.latitude,
        longitude=dealer_data.longitude,
        phone=dealer_data.phone.strip(),
        available_cylinders=dealer_data.available_cylinders,
        status="PENDING",
        is_active=True,
    )
    db.add(dealer)
    db.commit()
    db.refresh(dealer)
    return DealerLoginResponse(
        access_token=create_access_token(dealer.id),
        refresh_token=create_refresh_token(db, user_type="dealer", user_id=dealer.id),
        dealer=dealer_to_private_response(db, dealer),
    )


@router.post("/dealer/login", response_model=DealerLoginResponse)
def login_dealer(credentials: DealerCredentials, db: Session = Depends(get_db)):
    login_identifier = credentials.username.strip().lower()
    dealer = (
        db.query(Dealer)
        .filter((Dealer.username == login_identifier) | (Dealer.email == login_identifier))
        .first()
    )
    if not dealer or not dealer.is_active or not verify_password(credentials.password, dealer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid dealer username or password")
    return DealerLoginResponse(
        access_token=create_access_token(dealer.id),
        refresh_token=create_refresh_token(db, user_type="dealer", user_id=dealer.id),
        dealer=dealer_to_private_response(db, dealer),
    )


@router.post("/dealer/auth/google", response_model=DealerLoginResponse)
def google_auth_dealer(
    request: GoogleAuthRequest,
    db: Session = Depends(get_db),
    verifier=Depends(get_google_verifier),
):
    id_info = verifier(request.id_token)
    email = id_info.get("email", "").strip().lower()
    google_id = id_info.get("sub", "")

    dealer = None
    if google_id:
        dealer = db.query(Dealer).filter(Dealer.google_id == google_id).first()
    if not dealer and email:
        dealer = db.query(Dealer).filter(Dealer.email == email).first()

    if not dealer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No dealer account associated with this Google email. Please register your shop first.",
        )

    if not dealer.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Dealer account is inactive")

    if not dealer.google_id and google_id:
        dealer.google_id = google_id
        db.commit()
        db.refresh(dealer)

    return DealerLoginResponse(
        access_token=create_access_token(dealer.id),
        refresh_token=create_refresh_token(db, user_type="dealer", user_id=dealer.id),
        dealer=dealer_to_private_response(db, dealer),
    )


@router.get("/dealer/me", response_model=DealerPrivateRead)
def get_current_dealer_profile(
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    return dealer_to_private_response(db, current_dealer)


@router.put("/dealer/me", response_model=DealerPrivateRead)
def update_current_dealer_profile(
    dealer_data: DealerUpdate,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    current_dealer.name = dealer_data.name.strip()
    current_dealer.address = dealer_data.address.strip()
    current_dealer.phone = dealer_data.phone.strip()
    current_dealer.latitude = dealer_data.latitude
    current_dealer.longitude = dealer_data.longitude
    current_dealer.available_cylinders = dealer_data.available_cylinders
    db.commit()
    db.refresh(current_dealer)
    return dealer_to_private_response(db, current_dealer)


@router.delete("/dealer/me", response_model=DealerPrivateRead)
def deactivate_current_dealer(
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    current_dealer.is_active = False
    db.commit()
    db.refresh(current_dealer)
    return dealer_to_private_response(db, current_dealer)


@router.get("/dealer/me/dashboard", response_model=DealerDashboard)
def get_my_dashboard(
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    return build_dashboard(db, current_dealer)


@router.get("/dealer/{dealer_id}/dashboard", response_model=DealerDashboard)
def get_dashboard(
    dealer_id: int,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    dealer = queue_service.get_dealer_or_404(db, dealer_id)
    return build_dashboard(db, dealer)


@router.get("/dealer/{dealer_id}/queue", response_model=list[QueueItem])
def get_dealer_queue(
    dealer_id: int,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    return [
        QueueItem(
            id=token.id,
            token_number=token.token_number,
            status=token.status,
            customer_name=token.customer.name,
            customer_phone=token.customer.phone,
            created_at=token.created_at,
            called_at=token.called_at,
        )
        for token in queue_service.get_queue_items(db, dealer_id)
    ]


@router.post("/dealer/{dealer_id}/call-next", response_model=TokenRead)
def call_next(
    dealer_id: int,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    return queue_service.call_next_token(db, dealer_id)


@router.post("/dealer/{dealer_id}/token/{token_id}/serve", response_model=TokenRead)
def serve_token(
    dealer_id: int,
    token_id: int,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    return queue_service.serve_token(db, dealer_id, token_id)


@router.post("/dealer/{dealer_id}/token/{token_id}/skip", response_model=TokenRead)
def skip_token(
    dealer_id: int,
    token_id: int,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    return queue_service.skip_token(db, dealer_id, token_id)


@router.post("/dealer/{dealer_id}/token/{token_id}/no-show", response_model=TokenRead)
def no_show_token(
    dealer_id: int,
    token_id: int,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    return queue_service.mark_no_show_token(db, dealer_id, token_id)


@router.patch("/dealer/{dealer_id}/stock", response_model=DealerRead)
def patch_stock(
    dealer_id: int,
    stock: StockUpdate,
    current_dealer: Dealer = Depends(get_current_dealer),
    db: Session = Depends(get_db),
):
    require_approved_dealer(current_dealer)
    if dealer_id != current_dealer.id:
        raise HTTPException(status_code=403, detail="You can only manage your own dealer account")
    dealer = queue_service.update_stock(db, dealer_id, stock.available_cylinders)
    return dealer_to_response(db, dealer)
