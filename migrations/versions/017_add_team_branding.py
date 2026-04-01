from alembic import op
import sqlalchemy as sa

revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('teams', sa.Column('branding', sa.Text(), server_default='{}', nullable=True))
    except Exception as e:
        print(f"Error adding branding column: {e}")

def downgrade():
    try:
        op.drop_column('teams', 'branding')
    except Exception as e:
        print(f"Error dropping branding column: {e}")
