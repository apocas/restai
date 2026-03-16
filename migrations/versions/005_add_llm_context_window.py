from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('llms', sa.Column('context_window', sa.Integer(), default=4096))
    except Exception as e:
        print(f"Error adding context_window column: {e}")

def downgrade():
    try:
        op.drop_column('llms', 'context_window')
    except Exception as e:
        print(f"Error dropping context_window column: {e}")
