"""add_totp_2fa

Revision ID: add_totp_2fa
Revises: 2026_06_09_0001
Create Date: 2026-06-13 00:00:01

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "add_totp_2fa"
down_revision: str | None = "2026_06_09_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("users", sa.Column("totp_setup_at", sa.DateTime(), nullable=True))

    op.create_table(
        "backup_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("hashed_code", sa.String(64), nullable=False),
        sa.Column("used", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("backup_codes")
    op.drop_column("users", "totp_setup_at")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
