"""Widen key_hash columns for PBKDF2 salted hashes and add key_prefix index."""
import sqlalchemy as sa
from alembic import op


revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.alter_column('api_keys', 'key_hash', type_=sa.String(256), existing_type=sa.String(64))
    except Exception as e:
        print(f"Error widening api_keys.key_hash: {e}")

    try:
        op.alter_column('widgets', 'key_hash', type_=sa.String(256), existing_type=sa.String(64))
    except Exception as e:
        print(f"Error widening widgets.key_hash: {e}")

    try:
        op.create_index('ix_api_keys_key_prefix', 'api_keys', ['key_prefix'])
    except Exception as e:
        print(f"Error creating api_keys key_prefix index: {e}")

    try:
        op.create_index('ix_widgets_key_prefix', 'widgets', ['key_prefix'])
    except Exception as e:
        print(f"Error creating widgets key_prefix index: {e}")


def downgrade():
    try:
        op.drop_index('ix_widgets_key_prefix', table_name='widgets')
    except Exception:
        pass
    try:
        op.drop_index('ix_api_keys_key_prefix', table_name='api_keys')
    except Exception:
        pass
    try:
        op.alter_column('widgets', 'key_hash', type_=sa.String(64), existing_type=sa.String(256))
    except Exception:
        pass
    try:
        op.alter_column('api_keys', 'key_hash', type_=sa.String(64), existing_type=sa.String(256))
    except Exception:
        pass
