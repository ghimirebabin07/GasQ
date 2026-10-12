import asyncio
from collections import defaultdict
from typing import Any

from models.notification import Notification
from sqlalchemy.orm import Session


class NotificationBus:
    def __init__(self):
        self._subscribers: dict[tuple[str, str], set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, user_type: str, user_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[(user_type, str(user_id))].add(queue)
        return queue

    def unsubscribe(self, user_type: str, user_id: str, queue: asyncio.Queue):
        key = (user_type, str(user_id))
        if key in self._subscribers:
            self._subscribers[key].discard(queue)
            if not self._subscribers[key]:
                del self._subscribers[key]

    def broadcast(self, user_type: str, user_id: str, payload: dict[str, Any]):
        key = (user_type, str(user_id))
        for queue in list(self._subscribers.get(key, [])):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass


notification_bus = NotificationBus()


def create_notification(
    db: Session,
    *,
    user_type: str,
    user_id: str | int,
    notification_type: str,
    title: str,
    message: str,
    related_token_id: int | None = None,
    idempotency_key: str | None = None,
) -> Notification:
    if idempotency_key:
        existing = (
            db.query(Notification)
            .filter(Notification.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return existing

    notification = Notification(
        user_type=user_type,
        user_id=str(user_id),
        notification_type=notification_type,
        title=title,
        message=message,
        related_token_id=related_token_id,
        idempotency_key=idempotency_key,
    )
    db.add(notification)
    db.flush()

    # Dispatch to active real-time SSE listeners
    payload = {
        "id": notification.id,
        "type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "related_token_id": notification.related_token_id,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }
    notification_bus.broadcast(user_type, str(user_id), payload)
    return notification
