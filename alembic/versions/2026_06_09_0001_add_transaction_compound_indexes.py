"""add compound indexes on transactions (user_id + symbol, user_id + type)

Revision ID: 2026_06_09_0001
Revises: 2026_06_06_0001
Create Date: 2026-06-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "2026_06_09_0001"
down_revision: Union[str, None] = "2026_06_06_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_user_symbol",
        "transactions",
        ["user_id", "symbol"],
        unique=False,
        postgresql_where=None,
    )
    op.create_index(
        "ix_transactions_user_type",
        "transactions",
        ["user_id", "transaction_type"],
        unique=False,
        postgresql_where=None,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_user_symbol", table_name="transactions")
    op.drop_index("ix_transactions_user_type", table_name="transactions")
