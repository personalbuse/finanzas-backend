"""add_admin_logs_and_config

Revision ID: add_admin_logs_and_config
Revises: add_world_markets
Create Date: 2025-05-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_admin_logs_and_config'
down_revision: str = 'add_world_markets'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('admin_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        sa.Column('admin_username', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_logs_action', 'admin_logs', ['action'], unique=False)
    op.create_index('ix_admin_logs_created_at', 'admin_logs', ['created_at'], unique=False)

    op.create_table('system_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', name='uq_system_config_key'),
    )
    op.create_index('ix_system_config_key', 'system_config', ['key'], unique=True)

    op.execute("""
        INSERT INTO system_config (key, value, description) VALUES
        ('initial_balance', '10000', 'Balance inicial para nuevos usuarios'),
        ('course_bonus', '1000', 'Bonus por curso completado'),
        ('max_daily_transactions', '50', 'Límite de transacciones diarias por usuario'),
        ('maintenance_mode', 'false', 'Modo mantenimiento del sistema'),
        ('suspicious_threshold', '50000', 'Monto mínimo para considerar transacción sospechosa')
    """)


def downgrade() -> None:
    op.drop_table('system_config')
    op.drop_table('admin_logs')
