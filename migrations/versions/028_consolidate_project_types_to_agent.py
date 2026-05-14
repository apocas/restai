"""Consolidate legacy 'agent2' and 'inference' project types into 'agent'."""
from alembic import op


revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE projects SET type = 'agent' WHERE type IN ('agent2', 'inference')"
    )


def downgrade():
    # No reliable downgrade — original type isn't tracked. Manual repair only.
    pass
