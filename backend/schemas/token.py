from datetime import datetime

from models.token import TokenStatus
from pydantic import BaseModel, Field


class QueueJoin(BaseModel):
    dealer_id: int = Field(gt=0)


class TokenRead(BaseModel):
    id: int
    dealer_id: int
    customer_id: int
    token_number: int
    status: TokenStatus
    created_at: datetime
    called_at: datetime | None = None
    served_at: datetime | None = None

    model_config = {"from_attributes": True}


class QueueStatus(BaseModel):
    token: TokenRead
    dealer_name: str
    dealer_address: str
    dealer_available_cylinders: int
    current_serving_token: int | None
    people_ahead: int
    message: str


class QueueItem(BaseModel):
    id: int
    token_number: int
    status: TokenStatus
    customer_name: str
    customer_phone: str
    created_at: datetime
    called_at: datetime | None = None


class DealerDashboard(BaseModel):
    dealer_id: int
    dealer_name: str
    available_cylinders: int
    current_serving_token: int | None
    current_called_token_id: int | None
    waiting_count: int
    cylinders_sold_today: int = 0
    queue: list[QueueItem]
