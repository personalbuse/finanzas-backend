from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fix_cache_value_type'
down_revision: Union[str, None] = 'add_db_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
