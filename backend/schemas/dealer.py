import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

PASSWORD_ALLOWED_PATTERN = re.compile(r"^[A-Za-z\d@$!%*#?&._-]+$")


class DealerRead(BaseModel):
    id: int
    name: str
    address: str
    latitude: float | None
    longitude: float | None
    phone: str
    available_cylinders: int
    status: str = "APPROVED"
    is_active: bool
    created_at: datetime
    people_waiting: int = 0
    current_serving_token: int | None = None
    stock_message: str

    model_config = {"from_attributes": True}


class DealerPrivateRead(DealerRead):
    username: str | None = None
    email: str | None = None


class DealerCredentials(BaseModel):
    username: str = Field(min_length=4, max_length=255)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("username")
    @classmethod
    def validate_login_identifier(cls, value: str) -> str:
        if "@" in value:
            if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
                raise ValueError("Enter a valid email address")
            return value
        if not re.fullmatch(r"^[A-Za-z][A-Za-z0-9_]{3,39}$", value):
            raise ValueError("Dealer ID must start with a letter and use 4-40 letters, numbers, or underscore")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not PASSWORD_ALLOWED_PATTERN.fullmatch(value):
            raise ValueError("Password contains unsupported characters")
        if not any(character.isalpha() for character in value):
            raise ValueError("Password must include at least one letter")
        if not any(character.isdigit() for character in value):
            raise ValueError("Password must include at least one number")
        return value


class DealerProfileBase(BaseModel):
    name: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9 .,'&()-]{2,119}$")
    address: str = Field(min_length=3, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9 .,'/#&()-]{2,254}$")
    phone: str = Field(min_length=7, max_length=15, pattern=r"^\+?[0-9]{7,15}$")
    available_cylinders: int = Field(ge=0, le=10000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class DealerCreate(DealerCredentials, DealerProfileBase):
    email: str = Field(min_length=6, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DealerUpdate(DealerProfileBase):
    pass


class DealerLoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    dealer: DealerPrivateRead


class StockUpdate(BaseModel):
    available_cylinders: int = Field(ge=0, le=10000)
