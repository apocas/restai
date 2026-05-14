"""Drop the LLMDatabase.type column.

batch_alter_table is required so SQLite (no native DROP COLUMN before 3.35)
goes through the copy-and-rebuild path.
"""
import sqlalchemy as sa
from alembic import op


revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('llms') as batch_op:
        batch_op.drop_column('type')


def downgrade():
    with op.batch_alter_table('llms') as batch_op:
        batch_op.add_column(sa.Column('type', sa.String(255), nullable=True))
