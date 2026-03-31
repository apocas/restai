from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'retrieval_events',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('source', sa.String(500), nullable=False, index=True),
            sa.Column('score', sa.Float(), nullable=True),
            sa.Column('date', sa.DateTime(), nullable=False, index=True),
        )
    except Exception as e:
        print(f"Error creating retrieval_events: {e}")

def downgrade():
    try:
        op.drop_table('retrieval_events')
    except Exception as e:
        print(f"Error dropping retrieval_events: {e}")
