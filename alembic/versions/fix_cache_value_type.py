from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'fix_cache_value_type'
down_revision: str | None = 'add_db_indexes'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column('cache_data', 'value',
        existing_type=sa.String(length=1000),
        type_=sa.Text(),
        existing_nullable=False,
        postgresql_using='value::text'
    )


def downgrade() -> None:
    op.alter_column('cache_data', 'value',
        existing_type=sa.Text(),
        type_=sa.String(length=1000),
        existing_nullable=False,
    )
