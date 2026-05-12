from typing import Sequence, Union

from alembic import op


revision: str = 'add_db_indexes'
down_revision: Union[str, None] = 'initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_users_rol', 'users', ['rol'], unique=False)
    op.create_index('ix_users_is_active', 'users', ['is_active'], unique=False)
    op.create_index('ix_transactions_user_id', 'transactions', ['user_id'], unique=False)
    op.create_index('ix_transactions_created_at', 'transactions', ['created_at'], unique=False)
    op.create_index('ix_verification_codes_user_id', 'verification_codes', ['user_id'], unique=False)
    op.create_index('ix_verification_codes_used', 'verification_codes', ['used'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_verification_codes_used', table_name='verification_codes')
    op.drop_index('ix_verification_codes_user_id', table_name='verification_codes')
    op.drop_index('ix_transactions_created_at', table_name='transactions')
    op.drop_index('ix_transactions_user_id', table_name='transactions')
    op.drop_index('ix_users_is_active', table_name='users')
    op.drop_index('ix_users_rol', table_name='users')
