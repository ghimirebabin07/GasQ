from fastapi import HTTPException
from models.customer import Customer
from models.dealer import Dealer
from models.token import Token, TokenStatus
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from time_utils import utc_now

from services.audit_service import record_audit_log
from services.notification_service import create_notification

ACTIVE_STATUSES = [TokenStatus.WAITING, TokenStatus.CALLED]


def get_dealer_or_404(db: Session, dealer_id: int) -> Dealer:
    dealer = db.get(Dealer, dealer_id)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
    return dealer


def get_token_or_404(db: Session, token_id: int) -> Token:
    token = db.get(Token, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


def get_current_called_token(db: Session, dealer_id: int) -> Token | None:
    return (
        db.query(Token)
        .filter(Token.dealer_id == dealer_id, Token.status == TokenStatus.CALLED)
        .order_by(Token.called_at.asc(), Token.token_number.asc())
        .first()
    )


def get_waiting_count(db: Session, dealer_id: int) -> int:
    return (
        db.query(func.count(Token.id))
        .filter(Token.dealer_id == dealer_id, Token.status == TokenStatus.WAITING)
        .scalar()
        or 0
    )


def get_people_ahead(db: Session, token: Token) -> int:
    if token.status != TokenStatus.WAITING:
        return 0

    return (
        db.query(func.count(Token.id))
        .filter(
            Token.dealer_id == token.dealer_id,
            Token.status == TokenStatus.WAITING,
            Token.token_number < token.token_number,
        )
        .scalar()
        or 0
    )


def build_stock_message(dealer: Dealer) -> str:
    if dealer.available_cylinders <= 0:
        return "Currently Out of Stock"
    return f"{dealer.available_cylinders} cylinders available"


def get_next_token_number(db: Session, dealer_id: int) -> int:
    last_number = (
        db.query(func.max(Token.token_number))
        .filter(Token.dealer_id == dealer_id)
        .scalar()
    )
    return (last_number or 100) + 1


def get_active_token_for_customer(db: Session, customer_id: int) -> Token | None:
    return (
        db.query(Token)
        .filter(Token.customer_id == customer_id, Token.status.in_(ACTIVE_STATUSES))
        .order_by(Token.created_at.asc(), Token.id.asc())
        .first()
    )


def get_active_token_for_phone(db: Session, phone: str | None) -> Token | None:
    if not phone:
        return None
    return (
        db.query(Token)
        .filter(Token.customer_phone == phone, Token.status.in_(ACTIVE_STATUSES))
        .order_by(Token.created_at.asc(), Token.id.asc())
        .first()
    )


def raise_active_token_error(db: Session, token: Token) -> None:
    dealer = get_dealer_or_404(db, token.dealer_id)
    raise HTTPException(
        status_code=400,
        detail=f"You already have an active token at {dealer.name}",
    )


def create_token(db: Session, dealer_id: int, customer_id: int) -> Token:
    dealer = get_dealer_or_404(db, dealer_id)
    if not dealer.is_active or dealer.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Dealer is not approved")
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not customer.phone:
        raise HTTPException(
            status_code=400,
            detail="Phone number required before taking a token. Please add your Nepal phone number.",
        )

    existing_token = get_active_token_for_customer(db, customer_id)
    if not existing_token:
        existing_token = get_active_token_for_phone(db, customer.phone)
    if existing_token:
        raise_active_token_error(db, existing_token)

    stock_update = db.execute(
        update(Dealer)
        .where(
            Dealer.id == dealer_id,
            Dealer.is_active.is_(True),
            Dealer.available_cylinders > 0,
        )
        .values(available_cylinders=Dealer.available_cylinders - 1)
    )
    if stock_update.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="No cylinders available at this dealer")

    token = Token(
        dealer_id=dealer_id,
        customer_id=customer_id,
        customer_phone=customer.phone,
        token_number=get_next_token_number(db, dealer_id),
        status=TokenStatus.WAITING,
    )
    db.add(token)
    try:
        db.flush()
        record_audit_log(
            db,
            actor_type="customer",
            actor_id=customer_id,
            action="TOKEN_CREATED",
            entity_type="token",
            entity_id=token.id,
            new_value={
                "dealer_id": dealer_id,
                "customer_id": customer_id,
                "token_number": token.token_number,
                "status": token.status.value,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_token = get_active_token_for_customer(db, customer_id)
        if not existing_token:
            existing_token = get_active_token_for_phone(db, customer.phone)
        if existing_token:
            raise_active_token_error(db, existing_token)
        raise HTTPException(status_code=400, detail="Unable to create token")
    db.refresh(token)
    return token


def call_next_token(db: Session, dealer_id: int) -> Token:
    get_dealer_or_404(db, dealer_id)
    current_called = get_current_called_token(db, dealer_id)
    if current_called:
        raise HTTPException(status_code=400, detail="Resolve current token first")

    next_token = (
        db.query(Token)
        .filter(Token.dealer_id == dealer_id, Token.status == TokenStatus.WAITING)
        .order_by(Token.token_number.asc(), Token.created_at.asc())
        .first()
    )
    if not next_token:
        raise HTTPException(status_code=400, detail="No waiting customers")

    next_token.status = TokenStatus.CALLED
    next_token.called_at = utc_now()
    create_notification(
        db,
        user_type="customer",
        user_id=next_token.customer_id,
        notification_type="TOKEN_CALLED",
        title="Your token is called",
        message=f"Token {next_token.token_number} is now being served.",
        related_token_id=next_token.id,
        idempotency_key=f"token_called:{next_token.id}",
    )
    record_audit_log(
        db,
        actor_type="dealer",
        actor_id=dealer_id,
        action="TOKEN_CALLED",
        entity_type="token",
        entity_id=next_token.id,
        old_value={"status": TokenStatus.WAITING.value},
        new_value={"status": TokenStatus.CALLED.value, "called_at": next_token.called_at},
    )
    db.commit()
    db.refresh(next_token)
    return next_token


def serve_token(db: Session, dealer_id: int, token_id: int) -> Token:
    get_dealer_or_404(db, dealer_id)
    token = get_token_or_404(db, token_id)
    if token.dealer_id != dealer_id:
        raise HTTPException(status_code=404, detail="Token not found for this dealer")
    if token.status != TokenStatus.CALLED:
        raise HTTPException(status_code=400, detail="Only a CALLED token can be served")

    token.status = TokenStatus.SERVED
    token.served_at = utc_now()
    record_audit_log(
        db,
        actor_type="dealer",
        actor_id=dealer_id,
        action="TOKEN_SERVED",
        entity_type="token",
        entity_id=token.id,
        old_value={"status": TokenStatus.CALLED.value},
        new_value={"status": TokenStatus.SERVED.value, "served_at": token.served_at},
    )
    db.commit()
    db.refresh(token)
    return token


def skip_token(db: Session, dealer_id: int, token_id: int) -> Token:
    dealer = get_dealer_or_404(db, dealer_id)
    token = get_token_or_404(db, token_id)
    if token.dealer_id != dealer_id:
        raise HTTPException(status_code=404, detail="Token not found for this dealer")
    if token.status != TokenStatus.CALLED:
        raise HTTPException(status_code=400, detail="Only a CALLED token can be skipped")

    token.status = TokenStatus.SKIPPED
    dealer.available_cylinders += 1
    record_audit_log(
        db,
        actor_type="dealer",
        actor_id=dealer_id,
        action="TOKEN_SKIPPED",
        entity_type="token",
        entity_id=token.id,
        old_value={"status": TokenStatus.CALLED.value},
        new_value={"status": TokenStatus.SKIPPED.value},
    )
    db.commit()
    db.refresh(token)
    return token


def mark_no_show_token(db: Session, dealer_id: int, token_id: int) -> Token:
    dealer = get_dealer_or_404(db, dealer_id)
    token = get_token_or_404(db, token_id)
    if token.dealer_id != dealer_id:
        raise HTTPException(status_code=404, detail="Token not found for this dealer")
    if token.status != TokenStatus.CALLED:
        raise HTTPException(status_code=400, detail="Only a CALLED token can be marked as no-show")

    token.status = TokenStatus.NO_SHOW
    dealer.available_cylinders += 1
    record_audit_log(
        db,
        actor_type="dealer",
        actor_id=dealer_id,
        action="TOKEN_NO_SHOW",
        entity_type="token",
        entity_id=token.id,
        old_value={"status": TokenStatus.CALLED.value},
        new_value={"status": TokenStatus.NO_SHOW.value},
    )
    db.commit()
    db.refresh(token)
    return token


def cancel_token(db: Session, token_id: int) -> Token:
    token = get_token_or_404(db, token_id)
    if token.status != TokenStatus.WAITING:
        raise HTTPException(status_code=400, detail="Only a WAITING token can be cancelled")

    dealer = get_dealer_or_404(db, token.dealer_id)
    token.status = TokenStatus.CANCELLED
    dealer.available_cylinders += 1
    record_audit_log(
        db,
        actor_type="customer",
        actor_id=token.customer_id,
        action="TOKEN_CANCELLED",
        entity_type="token",
        entity_id=token.id,
        old_value={"status": TokenStatus.WAITING.value},
        new_value={"status": TokenStatus.CANCELLED.value},
    )
    db.commit()
    db.refresh(token)
    return token


def update_stock(db: Session, dealer_id: int, available_cylinders: int) -> Dealer:
    dealer = get_dealer_or_404(db, dealer_id)
    if available_cylinders < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")

    old_stock = dealer.available_cylinders
    dealer.available_cylinders = available_cylinders
    record_audit_log(
        db,
        actor_type="dealer",
        actor_id=dealer_id,
        action="STOCK_UPDATED",
        entity_type="dealer",
        entity_id=dealer_id,
        old_value={"available_cylinders": old_stock},
        new_value={"available_cylinders": available_cylinders},
    )
    db.commit()
    db.refresh(dealer)
    return dealer


def get_current_serving_number(db: Session, dealer_id: int) -> int | None:
    current_called = get_current_called_token(db, dealer_id)
    return current_called.token_number if current_called else None


def get_queue_items(db: Session, dealer_id: int) -> list[Token]:
    get_dealer_or_404(db, dealer_id)
    return (
        db.query(Token)
        .options(joinedload(Token.customer))
        .filter(Token.dealer_id == dealer_id)
        .filter(Token.status.in_([TokenStatus.WAITING, TokenStatus.CALLED]))
        .order_by(Token.token_number.asc(), Token.created_at.asc())
        .all()
    )
