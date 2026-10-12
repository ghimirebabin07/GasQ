import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from schemas.dealer import PASSWORD_ALLOWED_PATTERN

NEPAL_PHONE_REGEX = re.compile(r"^(?:\+?977[- ]?)?(9[78]\d{8})$")


def validate_nepal_phone_number(value: str | None) -> str:
    if not value:
        raise ValueError("Phone number is required")
    cleaned = value.strip().replace(" ", "").replace("-", "")
    match = NEPAL_PHONE_REGEX.match(cleaned)
    if not match:
        raise ValueError("Invalid Nepal phone number. Must be 10 digits starting with 97 or 98 (e.g. 9812345678 or +9779812345678)")
    return match.group(1)


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z][A-Za-z .'-]{1,99}$")
    phone: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=8, max_length=72, pattern=PASSWORD_ALLOWED_PATTERN.pattern)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_nepal_phone_number(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(character.isalpha() for character in value):
            raise ValueError("Password must include at least one letter")
        if not any(character.isdigit() for character in value):
            raise ValueError("Password must include at least one number")
        return value


class CustomerLogin(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=8, max_length=72, pattern=PASSWORD_ALLOWED_PATTERN.pattern)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_nepal_phone_number(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return CustomerCreate.validate_password(value)


class CustomerPhoneUpdate(BaseModel):
    phone: str = Field(min_length=7, max_length=20)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return validate_nepal_phone_number(value)


class CustomerRead(BaseModel):
    id: int
    name: str
    phone: str | None = None
    email: str | None = None
    is_phone_verified: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerLoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    customer: CustomerRead
