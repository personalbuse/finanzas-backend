"""add_world_markets

Revision ID: add_world_markets
Revises: fix_cache_value_type
Create Date: 2024-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_world_markets'
down_revision: str = 'fix_cache_value_type'
branch: Union[None, str] = None
depends_on: Union[None, Sequence[str]] = None


def upgrade() -> None:
    op.create_table(
        'world_indices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(30), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('country', sa.String(3), nullable=False),
        sa.Column('region', sa.String(50), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('current_value', sa.Numeric(15, 2), nullable=True),
        sa.Column('change', sa.Numeric(15, 4), nullable=True),
        sa.Column('change_percent', sa.Numeric(15, 4), nullable=True),
        sa.Column('high', sa.Numeric(15, 2), nullable=True),
        sa.Column('low', sa.Numeric(15, 2), nullable=True),
        sa.Column('previous_close', sa.Numeric(15, 2), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol')
    )
    op.create_index('ix_world_indices_symbol', 'world_indices', ['symbol'])
    op.create_index('ix_world_indices_country', 'world_indices', ['country'])
    op.create_index('ix_world_indices_region', 'world_indices', ['region'])

    op.create_table(
        'index_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('index_symbol', sa.String(30), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Numeric(15, 2), nullable=True),
        sa.Column('high', sa.Numeric(15, 2), nullable=True),
        sa.Column('low', sa.Numeric(15, 2), nullable=True),
        sa.Column('close', sa.Numeric(15, 2), nullable=True),
        sa.Column('volume', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['index_symbol'], ['world_indices.symbol'], ondelete='CASCADE')
    )
    op.create_index('ix_index_history_index_symbol', 'index_history', ['index_symbol'])
    op.create_index('ix_index_history_date', 'index_history', ['date'])
    op.create_unique_constraint('unique_index_date', 'index_history', ['index_symbol', 'date'])

    op.create_table(
        'international_stocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('name', sa.String(150), nullable=False),
        sa.Column('exchange', sa.String(50), nullable=False),
        sa.Column('country', sa.String(3), nullable=False),
        sa.Column('region', sa.String(30), nullable=False),
        sa.Column('sector', sa.String(50), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('current_price', sa.Numeric(15, 4), nullable=True),
        sa.Column('change', sa.Numeric(15, 4), nullable=True),
        sa.Column('change_percent', sa.Numeric(15, 4), nullable=True),
        sa.Column('previous_close', sa.Numeric(15, 4), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol')
    )
    op.create_index('ix_international_stocks_symbol', 'international_stocks', ['symbol'])
    op.create_index('ix_international_stocks_country', 'international_stocks', ['country'])
    op.create_index('ix_international_stocks_region', 'international_stocks', ['region'])


def downgrade() -> None:
    op.drop_table('international_stocks')
    op.drop_table('index_history')
    op.drop_table('world_indices')