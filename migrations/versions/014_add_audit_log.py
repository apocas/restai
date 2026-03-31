from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'audit_log',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('username', sa.String(255), nullable=True),
            sa.Column('action', sa.String(10), nullable=False),
            sa.Column('resource', sa.String(500), nullable=False),
            sa.Column('status_code', sa.Integer(), nullable=False),
            sa.Column('date', sa.DateTime(), nullable=False, index=True),
        )
    except Exception as e:
        print(f"Error creating audit_log: {e}")

def downgrade():
    try:
        op.drop_table('audit_log')
    except Exception as e:
        print(f"Error dropping audit_log: {e}")
