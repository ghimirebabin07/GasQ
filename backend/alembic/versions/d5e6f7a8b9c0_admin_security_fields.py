"""admin_security_fields: Add admin session-security fields to admin_users.

Revision ID: d5e6f7a8b9c0
Revises: c94d2a648be7
Create Date: 2026-10-12 16:50:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c94d2a648be7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("admin_users")}

    with op.batch_alter_table("admin_users") as batch_op:
        if "is_active" not in columns:
            batch_op.add_column(
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1")
            )
        if "totp_secret" not in columns:
            batch_op.add_column(sa.Column("totp_secret", sa.String(length=64), nullable=True))
        if "failed_login_attempts" not in columns:
            batch_op.add_column(
                sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0")
            )
        if "locked_until" not in columns:
            batch_op.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.drop_column("locked_until")
        batch_op.drop_column("failed_login_attempts")
        batch_op.drop_column("totp_secret")
        batch_op.drop_column("is_active")
