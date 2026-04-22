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
"""
import sqlalchemy as sa
from alembic import op


revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'image_generators',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('name', sa.String(255), nullable=False, unique=True, index=True),
            sa.Column('class_name', sa.String(64), nullable=False),
            sa.Column('options', sa.Text(), nullable=True, server_default='{}'),
            sa.Column('privacy', sa.String(32), nullable=False, server_default='public'),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
    except Exception as e:
        print(f"Error creating image_generators table: {e}")

    # Drop dalle access from any team that had it — the dalle3 generator
    # is being removed in the same release.
    try:
        op.execute(
            "DELETE FROM teams_image_generators WHERE generator_name IN ('dalle', 'dalle3', 'dall-e-3')"
        )
    except Exception as e:
        print(f"Error pruning dalle from teams_image_generators: {e}")

    # Drop the platform-wide OpenAI API key — credentials now live per
    # generator (encrypted inside `image_generators.options`).
    try:
        op.execute("DELETE FROM settings WHERE key = 'openai_api_key'")
    except Exception as e:
        print(f"Error dropping openai_api_key setting: {e}")


def downgrade():
    try:
        op.drop_table('image_generators')
    except Exception as e:
        print(f"Error dropping image_generators table: {e}")
