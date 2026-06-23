"""add_phone_number_to_users

Revision ID: add_phone_number
Revises: add_totp_2fa
Create Date: 2026-06-22 00:00:01

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "add_phone_number"
down_revision: str | None = "add_totp_2fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "phone_number")
