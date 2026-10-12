from datetime import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: int
    user_type: str
    user_id: str
    notification_type: str
    title: str
    message: str
    related_token_id: int | None = None
    idempotency_key: str | None = None
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
