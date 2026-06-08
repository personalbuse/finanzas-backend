"""add password_version and completed_modules

Revision ID: 2026_06_06_0001
Revises: add_admin_logs_and_config
Create Date: 2026-06-06 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2026_06_06_0001"
down_revision: Union[str, None] = "add_admin_logs_and_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "completed_modules",
        sa.Column("id", sa.Integer(), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("module_id", sa.String(length=10), nullable=False),
        sa.Column("completed_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "module_id", name="uq_completed_user_module"),
    )

    op.create_index(
        "ix_transactions_user_created",
        "transactions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_created", table_name="transactions")
    op.drop_table("completed_modules")
    op.drop_column("users", "password_version")
