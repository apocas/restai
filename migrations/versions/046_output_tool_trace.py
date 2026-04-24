"""Per-tool trace column on `output`.

Adds ``output.tool_trace`` (nullable JSON-encoded text) so the log
viewer can render each agent's tool-call timeline. Populated by the
agent loop in ``restai/projects/agent.py``; see ``log_inference`` in
``restai/tools.py`` for persistence.
"""
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
