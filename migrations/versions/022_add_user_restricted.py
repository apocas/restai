from alembic import op
import sqlalchemy as sa

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('users', sa.Column('is_restricted', sa.Boolean(), server_default='0', nullable=True))
    except Exception as e:
        print(f"Error adding is_restricted: {e}")

def downgrade():
    try:
        op.drop_column('users', 'is_restricted')
    except Exception as e:
        print(f"Error dropping is_restricted: {e}")
