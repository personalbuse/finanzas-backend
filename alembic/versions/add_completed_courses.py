"""
alembic/versions/add_completed_courses.py

Add completed_courses column to users table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_completed_courses'
down_revision: Union[str, None] = 'initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('completed_courses', sa.Integer(), nullable=True, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('users', 'completed_courses')