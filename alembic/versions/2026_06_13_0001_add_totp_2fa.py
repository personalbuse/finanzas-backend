"""add_totp_2fa

Revision ID: add_totp_2fa
Revises: 2026_06_09_0001_add_transaction_compound_indexes
Create Date: 2026-06-13 00:00:01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_totp_2fa"
down_revision: Union[str, None] = "2026_06_09_0001_add_transaction_compound_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.create_index(op.f("ix_backup_codes_id"), "backup_codes", ["id"])
    op.create_index(op.f("ix_backup_codes_user_id"), "backup_codes", ["user_id"])


def downgrade() -> None:
    op.drop_table("backup_codes")
    op.drop_column("users", "totp_setup_at")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
