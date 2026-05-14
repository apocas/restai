"""Image generator registry. Drops legacy dalle access + platform openai_api_key setting.

MySQL-safety notes (see 035):
- No `server_default` on TEXT (`options`) — pre-8.0.13 MySQL rejects them.
- `key` is a MySQL reserved word — backtick-quote in raw SQL.
- No broad try/except around create_table — silent failures advance alembic_version with no table.
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

    op.execute(
        "DELETE FROM teams_image_generators WHERE generator_name IN ('dalle', 'dalle3', 'dall-e-3')"
    )

    # `key` is a MySQL reserved word — backticks required.
    op.execute("DELETE FROM settings WHERE `key` = 'openai_api_key'")


def downgrade():
    op.drop_table('image_generators')
