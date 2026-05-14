"""Add output.tool_trace (JSON-encoded agent tool-call timeline)."""
import sqlalchemy as sa
from alembic import op


revision = '046'
down_revision = '045'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column('output', sa.Column('tool_trace', sa.Text(), nullable=True))
    except Exception:
        pass


def downgrade():
    try:
        op.drop_column('output', 'tool_trace')
    except Exception:
        pass
