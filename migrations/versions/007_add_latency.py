from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('output', sa.Column('latency_ms', sa.Integer(), nullable=True))
    except Exception as e:
        print(f"Error adding latency_ms column: {e}")

def downgrade():
    try:
        op.drop_column('output', 'latency_ms')
    except Exception as e:
        print(f"Error dropping latency_ms column: {e}")
