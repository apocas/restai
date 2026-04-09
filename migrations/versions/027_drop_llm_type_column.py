"""Drop the LLMDatabase.type column.

The LLM `type` field (chat / completion / qa / vision) was metadata-only —
no backend code branched on it for behavior. Vision-capable models are
already identified by their `class_name` (OllamaMultiModal, GeminiMultiModal,
etc.) and model name patterns, not by this field.

Uses `batch_alter_table` so SQLite (which doesn't natively support
ALTER TABLE DROP COLUMN before 3.35) goes through the copy-and-rebuild path.
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
