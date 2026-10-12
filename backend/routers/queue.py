from auth import get_current_customer
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from models.customer import Customer
from schemas.token import QueueJoin, QueueStatus, TokenRead
from services import queue_service
from sqlalchemy.orm import Session

router = APIRouter(tags=["queue"])


def build_queue_status(db: Session, token_id: int) -> QueueStatus:
    token = queue_service.get_token_or_404(db, token_id)
    dealer = queue_service.get_dealer_or_404(db, token.dealer_id)

    message = "Waiting in queue."
    if token.status == "CALLED":
        message = "Your turn is now available."
    elif token.status == "SERVED":
        message = "Your LPG collection is completed."
    elif token.status == "SKIPPED":
        message = "This token was skipped by the dealer."
    elif token.status == "CANCELLED":
        message = "This token was cancelled."

    return QueueStatus(
        token=token,
        dealer_name=dealer.name,
        dealer_address=dealer.address,
        dealer_available_cylinders=dealer.available_cylinders,
        current_serving_token=queue_service.get_current_serving_number(db, token.dealer_id),
        people_ahead=queue_service.get_people_ahead(db, token),
        message=message,
    )


def require_token_owner(token_id: int, customer: Customer, db: Session) -> None:
    token = queue_service.get_token_or_404(db, token_id)
    if token.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Token not found")


@router.post("/queue/join", response_model=QueueStatus)
def join_queue(
    join_data: QueueJoin,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    token = queue_service.create_token(db, join_data.dealer_id, current_customer.id)
    return build_queue_status(db, token.id)


@router.get("/queue/{token_id}", response_model=QueueStatus)
def get_queue_status(
    token_id: int,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    require_token_owner(token_id, current_customer, db)
    return build_queue_status(db, token_id)


@router.post("/queue/{token_id}/cancel", response_model=TokenRead)
def cancel_token(
    token_id: int,
    current_customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    require_token_owner(token_id, current_customer, db)
    return queue_service.cancel_token(db, token_id)
