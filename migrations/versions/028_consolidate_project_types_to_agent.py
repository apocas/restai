"""Consolidate the agent2 / inference / agent project types into a single 'agent'.

History this collapses:
- The standalone agent2 project type was a sibling of the legacy llamaindex
  agent. We renamed it to 'inference', then renamed inference to 'agent' as
  the canonical name. The new agent is powered by the non-llamaindex
  restai/agent2/ runtime; the legacy llamaindex agent.py is gone.

This migration rewrites any leftover rows so they all land on the canonical
'agent' type. Existing 'agent' rows are unchanged (they keep their type but
now use the new code path on disk).

Chat history continuity: existing chat sessions stored under the legacy
agent's llamaindex chat_store will not carry over to the new agent2-backed
session store. Users start fresh on their next chat.
"""
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
    # No reliable downgrade — we don't track which agent rows were originally
    # agent2 or inference. Manual repair only.
    pass
