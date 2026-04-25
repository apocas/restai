"""Speech-to-text model registry.

New `speech_to_text` table managed via the dedicated admin page. Local
workers (auto-seeded from `restai/audio/workers/*.py`) sit alongside
external providers (OpenAI Whisper, Google STT, Deepgram, AssemblyAI),
each with its own encrypted credentials in `options`.

The legacy `Audio Gen` menu entry is removed in this same release; team
grants in `teams_audio_generators` continue to work unchanged (still
keyed by the generator's `name`).

MySQL-safety notes (see 035 for the full story):
- TEXT columns drop `server_default` — MySQL rejects defaults on
  TEXT/BLOB. `options` is set explicitly by the application on insert.
- The broad try/except around `create_table` was removed.
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
