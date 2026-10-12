from typing import Any

from pydantic import BaseModel, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=10)


class EmailOtpSendRequest(BaseModel):
    email: str = Field(min_length=6, max_length=255, pattern=EMAIL_PATTERN)


class EmailOtpVerifyRequest(BaseModel):
    email: str = Field(min_length=6, max_length=255, pattern=EMAIL_PATTERN)
    code: str = Field(min_length=4, max_length=10)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict[str, Any]
