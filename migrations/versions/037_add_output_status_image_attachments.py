"""Add status / error / image / attachments columns to the inference log.

Lets the log viewer record failures (budget / rate limit / LLM error / tool
crash / guard block) and user-supplied images + file attachments. Previously
these paths either silently dropped the row or kept only the happy-path
question/answer pair.
"""
import sqlalchemy as sa
from alembic import op


revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.add_column(
            'output',
            sa.Column('status', sa.String(32), nullable=False, server_default='success'),
        )
    except Exception as e:
        print(f"Error adding output.status: {e}")

    try:
        op.create_index('ix_output_status', 'output', ['status'])
    except Exception as e:
        print(f"Error indexing output.status: {e}")

    for col_name, col_type in (
        ('error', sa.Text()),
        ('image', sa.Text()),
        ('attachments', sa.Text()),
    ):
        try:
            op.add_column('output', sa.Column(col_name, col_type, nullable=True))
        except Exception as e:
            print(f"Error adding output.{col_name}: {e}")


def downgrade():
    for col_name in ('attachments', 'image', 'error'):
        try:
            op.drop_column('output', col_name)
        except Exception as e:
            print(f"Error dropping output.{col_name}: {e}")
    try:
        op.drop_index('ix_output_status', table_name='output')
    except Exception as e:
        print(f"Error dropping ix_output_status: {e}")
    try:
        op.drop_column('output', 'status')
    except Exception as e:
        print(f"Error dropping output.status: {e}")
