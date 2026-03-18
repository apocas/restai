from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('teams', sa.Column('budget', sa.Float(), default=-1.0))
        op.execute("UPDATE teams SET budget = -1.0 WHERE budget IS NULL")
    except Exception as e:
        print(f"Error adding budget column: {e}")

def downgrade():
    try:
        op.drop_column('teams', 'budget')
    except Exception as e:
        print(f"Error dropping budget column: {e}")
