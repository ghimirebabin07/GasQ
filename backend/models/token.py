from datetime import datetime
from enum import Enum

from database import Base
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from time_utils import utc_now


class TokenStatus(str, Enum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Token(Base):
    __tablename__ = "tokens"
    __table_args__ = (
        Index(
            "ux_tokens_active_customer",
            "customer_id",
            unique=True,
            postgresql_where=text("status IN ('WAITING', 'CALLED')"),
            sqlite_where=text("status IN ('WAITING', 'CALLED')"),
        ),
        Index(
            "ux_tokens_active_phone",
            "customer_phone",
            unique=True,
            postgresql_where=text("status IN ('WAITING', 'CALLED') AND customer_phone IS NOT NULL"),
            sqlite_where=text("status IN ('WAITING', 'CALLED') AND customer_phone IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"), index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    token_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TokenStatus] = mapped_column(SqlEnum(TokenStatus), default=TokenStatus.WAITING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    served_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    dealer = relationship("Dealer", back_populates="tokens")
    customer = relationship("Customer", back_populates="tokens")
