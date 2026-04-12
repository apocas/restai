"""Widen key_hash columns for PBKDF2 salted hashes and add key_prefix index."""
import sqlalchemy as sa
from alembic import op


revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade():
    try:
        with op.batch_alter_table('api_keys') as batch_op:
            batch_op.alter_column('key_hash', type_=sa.String(256), existing_type=sa.String(64))
    except Exception as e:
        print(f"Note: api_keys.key_hash resize skipped: {e}")

    try:
        with op.batch_alter_table('widgets') as batch_op:
            batch_op.alter_column('key_hash', type_=sa.String(256), existing_type=sa.String(64))
    except Exception as e:
        print(f"Note: widgets.key_hash resize skipped: {e}")

    try:
        op.create_index('ix_api_keys_key_prefix', 'api_keys', ['key_prefix'])
    except Exception as e:
        print(f"Note: api_keys key_prefix index skipped: {e}")

    try:
        op.create_index('ix_widgets_key_prefix', 'widgets', ['key_prefix'])
    except Exception as e:
        print(f"Note: widgets key_prefix index skipped: {e}")


def downgrade():
    try:
        op.drop_index('ix_widgets_key_prefix', table_name='widgets')
    except Exception:
        pass
    try:
        op.drop_index('ix_api_keys_key_prefix', table_name='api_keys')
    except Exception:
        pass
