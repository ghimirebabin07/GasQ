import asyncio
import logging
from datetime import timedelta

from database import SessionLocal
from models.dealer import Dealer
from models.notification import Notification
from models.token import Token, TokenStatus
from services.audit_service import record_audit_log
from services.notification_service import create_notification
from sqlalchemy.orm import Session
from time_utils import utc_now

logger = logging.getLogger("gasq.scheduler")


def expire_no_show_tokens(db: Session, expiry_minutes: int = 15) -> int:
    cutoff = utc_now() - timedelta(minutes=expiry_minutes)
    expired_tokens = (
        db.query(Token)
        .filter(
            Token.status == TokenStatus.CALLED,
            Token.called_at.is_not(None),
            Token.called_at <= cutoff,
        )
        .all()
    )

    count = 0
    for token in expired_tokens:
        old_status = token.status.value
        token.status = TokenStatus.NO_SHOW

        # Release reserved cylinder back to dealer stock
        dealer = db.get(Dealer, token.dealer_id)
        if dealer:
            dealer.available_cylinders += 1

        record_audit_log(
            db,
            actor_type="system",
            actor_id="scheduler",
            action="TOKEN_EXPIRED_NO_SHOW",
            entity_type="token",
            entity_id=token.id,
            old_value={"status": old_status},
            new_value={"status": token.status.value, "released_stock": 1},
        )

        shop_name = dealer.name if dealer else "the shop"
        create_notification(
            db,
            user_type="customer",
            user_id=str(token.customer_id),
            notification_type="TOKEN_EXPIRED",
            title="Token Expired",
            message=f"Your token #{token.token_number} at {shop_name} has expired because it was not collected within {expiry_minutes} minutes.",
            related_token_id=token.id,
            idempotency_key=f"token_expired_no_show_{token.id}",
        )
        count += 1

    if count > 0:
        db.commit()
        logger.info("Expired %d no-show tokens and released stock", count)
    return count


def check_and_send_position_reminders(db: Session) -> int:
    # Find all waiting tokens
    waiting_tokens = (
        db.query(Token)
        .filter(Token.status == TokenStatus.WAITING)
        .order_by(Token.dealer_id, Token.token_number)
        .all()
    )

    reminders_sent = 0
    for token in waiting_tokens:
        # Calculate how many people are ahead
        people_ahead = (
            db.query(Token)
            .filter(
                Token.dealer_id == token.dealer_id,
                Token.status == TokenStatus.WAITING,
                Token.token_number < token.token_number,
            )
            .count()
        )

        if people_ahead == 3:
            dealer = db.get(Dealer, token.dealer_id)
            shop_name = dealer.name if dealer else "the dealer"
            idempotency_key = f"reminder_pos_3_token_{token.id}"

            already_sent = (
                db.query(Notification)
                .filter(Notification.idempotency_key == idempotency_key)
                .first()
            )
            if not already_sent:
                create_notification(
                    db,
                    user_type="customer",
                    user_id=str(token.customer_id),
                    notification_type="QUEUE_REMINDER",
                    title="Queue Reminder",
                    message=f"You are 3rd in line at {shop_name} for token #{token.token_number}. Please be ready.",
                    related_token_id=token.id,
                    idempotency_key=idempotency_key,
                )
                reminders_sent += 1

    if reminders_sent > 0:
        db.commit()
    return reminders_sent


async def background_scheduler_loop(interval_seconds: int = 30):
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(run_scheduler_iteration)
        except Exception as exc:
            logger.error("Error in background scheduler iteration: %s", exc)


def run_scheduler_iteration() -> None:
    with SessionLocal() as db:
        expire_no_show_tokens(db, expiry_minutes=15)
        check_and_send_position_reminders(db)
