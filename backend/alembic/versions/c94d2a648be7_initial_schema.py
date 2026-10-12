"""initial_schema: Baseline migration creating all GasQ tables, constraints, and indexes.

Revision ID: c94d2a648be7
Revises:
Create Date: 2026-10-12 07:57:39
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c94d2a648be7"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. admin_users
    if "admin_users" not in existing_tables:
        op.create_table(
            "admin_users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)
        op.create_index("ix_admin_users_id", "admin_users", ["id"], unique=False)

    # 2. dealers
    if "dealers" not in existing_tables:
        op.create_table(
            "dealers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("username", sa.String(length=40), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("google_id", sa.String(length=255), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=True),
            sa.Column("address", sa.String(length=255), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("phone", sa.String(length=30), nullable=False),
            sa.Column("available_cylinders", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="APPROVED"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("available_cylinders >= 0", name="ck_dealers_available_cylinders_nonnegative"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_dealers_id", "dealers", ["id"], unique=False)
        op.create_index("ix_dealers_username", "dealers", ["username"], unique=True)
        op.create_index("ix_dealers_email", "dealers", ["email"], unique=True)
        op.create_index("ix_dealers_google_id", "dealers", ["google_id"], unique=True)

    # 3. customers
    if "customers" not in existing_tables:
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("phone", sa.String(length=30), nullable=True),
            sa.Column("is_phone_verified", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("google_id", sa.String(length=255), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_customers_id", "customers", ["id"], unique=False)
        op.create_index("ix_customers_phone", "customers", ["phone"], unique=False)
        op.create_index("ix_customers_email", "customers", ["email"], unique=True)
        op.create_index("ix_customers_google_id", "customers", ["google_id"], unique=True)

    # 4. tokens
    if "tokens" not in existing_tables:
        op.create_table(
            "tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("dealer_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("customer_phone", sa.String(length=30), nullable=True),
            sa.Column("token_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="WAITING"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("called_at", sa.DateTime(), nullable=True),
            sa.Column("served_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["dealer_id"], ["dealers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tokens_id", "tokens", ["id"], unique=False)
        op.create_index("ix_tokens_dealer_id", "tokens", ["dealer_id"], unique=False)
        op.create_index("ix_tokens_customer_id", "tokens", ["customer_id"], unique=False)
        op.create_index("ix_tokens_customer_phone", "tokens", ["customer_phone"], unique=False)
        op.create_index(
            "ux_tokens_active_customer",
            "tokens",
            ["customer_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('WAITING', 'CALLED')"),
            sqlite_where=sa.text("status IN ('WAITING', 'CALLED')"),
        )
        op.create_index(
            "ux_tokens_active_phone",
            "tokens",
            ["customer_phone"],
            unique=True,
            postgresql_where=sa.text("status IN ('WAITING', 'CALLED') AND customer_phone IS NOT NULL"),
            sqlite_where=sa.text("status IN ('WAITING', 'CALLED') AND customer_phone IS NOT NULL"),
        )

    # 5. audit_logs
    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("actor_type", sa.String(length=30), nullable=False),
            sa.Column("actor_id", sa.String(length=120), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=120), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_logs_id", "audit_logs", ["id"], unique=False)
        op.create_index("ix_audit_logs_actor_type", "audit_logs", ["actor_type"], unique=False)
        op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"], unique=False)
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
        op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"], unique=False)
        op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"], unique=False)
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)

    # 6. notifications
    if "notifications" not in existing_tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_type", sa.String(length=30), nullable=False),
            sa.Column("user_id", sa.String(length=120), nullable=False),
            sa.Column("notification_type", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("related_token_id", sa.Integer(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=160), nullable=True),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_notifications_id", "notifications", ["id"], unique=False)
        op.create_index("ix_notifications_user_type", "notifications", ["user_type"], unique=False)
        op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)
        op.create_index("ix_notifications_notification_type", "notifications", ["notification_type"], unique=False)
        op.create_index("ix_notifications_related_token_id", "notifications", ["related_token_id"], unique=False)
        op.create_index("ix_notifications_idempotency_key", "notifications", ["idempotency_key"], unique=True)
        op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)

    # 7. refresh_tokens
    if "refresh_tokens" not in existing_tables:
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_type", sa.String(length=20), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"], unique=False)
        op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
        op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    # 8. email_otps
    if "email_otps" not in existing_tables:
        op.create_table(
            "email_otps",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("lockout_until", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_email_otps_id", "email_otps", ["id"], unique=False)
        op.create_index("ix_email_otps_email", "email_otps", ["email"], unique=False)


def downgrade() -> None:
    op.drop_table("email_otps")
    op.drop_table("refresh_tokens")
    op.drop_table("notifications")
    op.drop_table("audit_logs")
    op.drop_table("tokens")
    op.drop_table("customers")
    op.drop_table("dealers")
    op.drop_table("admin_users")
