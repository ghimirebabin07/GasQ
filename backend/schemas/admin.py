from datetime import datetime

from pydantic import BaseModel, Field


class AdminLogin(BaseModel):
    email: str = Field(min_length=4, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    totp_code: str | None = Field(default=None, max_length=10)


class AdminLoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    csrf_token: str | None = None
    requires_2fa: bool = False


class AdminDealerRead(BaseModel):
    id: int
    name: str
    username: str | None = None
    email: str | None = None
    address: str
    phone: str
    available_cylinders: int
    status: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminNotificationRead(BaseModel):
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


class Admin2FASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class Admin2FAEnableRequest(BaseModel):
    totp_code: str = Field(min_length=6, max_length=6)


class AdminReauthRequest(BaseModel):
    password: str = Field(min_length=8, max_length=255)
