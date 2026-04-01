from alembic import op
import sqlalchemy as sa

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('users', sa.Column('totp_secret', sa.String(500), nullable=True))
        op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), server_default='0', nullable=True))
        op.add_column('users', sa.Column('totp_recovery_codes', sa.Text(), nullable=True))
    except Exception as e:
        print(f"Error adding TOTP columns: {e}")

def downgrade():
    try:
        op.drop_column('users', 'totp_secret')
        op.drop_column('users', 'totp_enabled')
        op.drop_column('users', 'totp_recovery_codes')
    except Exception as e:
        print(f"Error dropping TOTP columns: {e}")
