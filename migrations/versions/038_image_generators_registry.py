"""Image generator registry.

New `image_generators` table that admins can CRUD via the dedicated
management page. Local workers (under `restai/image/workers/*.py`) get
auto-seeded with `class_name='local'` on startup; external providers
(OpenAI, OpenAI-compat, Google) live alongside them with their own
encrypted credentials in `options`.

Also drops legacy bits:
- `dalle` rows from `teams_image_generators` — the dalle3 generator is
  removed in this same release. Existing teams lose access; admin
  re-grants after creating a new OpenAI image generator.
- `openai_api_key` from the platform `settings` table — credentials now
  live per-generator inside `options`.

MySQL-safety notes (see 035 for the full story):
- TEXT columns must NOT carry a `server_default` (`options`, originally
  defaulted to `'{}'`, broke MySQL upgrades). The application writes a
  value before insert, so NULL-allowed is enough.
- `key` is a MySQL reserved word — the cleanup `DELETE FROM settings`
  must backtick-quote it. The bare form parses on SQLite and fails on
  MySQL with a syntax error.
- Broad try/except wrappers were removed — silent failures here let
  alembic mark the migration done while the table was never created.
"""
import sqlalchemy as sa
from alembic import op


revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'image_generators',
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

    # Drop dalle access from any team that had it — the dalle3 generator
    # is being removed in the same release.
    op.execute(
        "DELETE FROM teams_image_generators WHERE generator_name IN ('dalle', 'dalle3', 'dall-e-3')"
    )

    # Drop the platform-wide OpenAI API key — credentials now live per
    # generator (encrypted inside `image_generators.options`). `key` is a
    # MySQL reserved word, so it MUST be backtick-quoted.
    op.execute("DELETE FROM settings WHERE `key` = 'openai_api_key'")


def downgrade():
    op.drop_table('image_generators')
