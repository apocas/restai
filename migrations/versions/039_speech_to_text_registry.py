"""Speech-to-text model registry.

MySQL-safety notes (see 035):
- No `server_default` on TEXT (`options`) — pre-8.0.13 MySQL rejects them.
- No broad try/except around create_table — silent failures advance alembic_version with no table.
"""
import sqlalchemy as sa
from alembic import op


revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'speech_to_text',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('class_name', sa.String(64), nullable=False),
        sa.Column('options', sa.Text(), nullable=True),
        sa.Column('privacy', sa.String(32), nullable=False, server_default='public'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('speech_to_text')
