"""add_phone_and_sms_preferences

Revision ID: add_phone_sms
Revises: add_totp_2fa
Create Date: 2026-06-22 00:00:01

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "add_phone_sms"
down_revision: str | None = "add_totp_2fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("phone_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("register_channel", sa.String(10), server_default=sa.text("'email'"), nullable=False))
    op.add_column("users", sa.Column("login_2fa_method", sa.String(15), server_default=sa.text("'authenticator'"), nullable=False))


def downgrade() -> None:
    op.drop_column("users", "login_2fa_method")
    op.drop_column("users", "register_channel")
    op.drop_column("users", "phone_confirmed")
    op.drop_column("users", "phone_number")
