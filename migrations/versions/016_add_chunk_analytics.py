from alembic import op
import sqlalchemy as sa

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('retrieval_events', sa.Column('chunk_id', sa.String(255), nullable=True, index=True))
        op.add_column('retrieval_events', sa.Column('chunk_token_length', sa.Integer(), nullable=True))
        op.add_column('retrieval_events', sa.Column('chunk_text_length', sa.Integer(), nullable=True))
    except Exception as e:
        print(f"Error adding chunk analytics columns: {e}")

def downgrade():
    try:
        op.drop_column('retrieval_events', 'chunk_id')
        op.drop_column('retrieval_events', 'chunk_token_length')
        op.drop_column('retrieval_events', 'chunk_text_length')
    except Exception as e:
        print(f"Error dropping chunk analytics columns: {e}")
