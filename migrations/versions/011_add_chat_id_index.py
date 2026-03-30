from alembic import op

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_index('ix_output_chat_id', 'output', ['chat_id'])
    except Exception as e:
        print(f"Error creating chat_id index: {e}")
    try:
        op.create_index('ix_output_project_id', 'output', ['project_id'])
    except Exception as e:
        print(f"Error creating project_id index: {e}")

def downgrade():
    try:
        op.drop_index('ix_output_chat_id', 'output')
    except Exception as e:
        print(f"Error dropping chat_id index: {e}")
    try:
        op.drop_index('ix_output_project_id', 'output')
    except Exception as e:
        print(f"Error dropping project_id index: {e}")
