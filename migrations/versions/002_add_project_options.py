from sqlalchemy import text, Column, Text
from alembic import op

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    # Add options column to projects table
    try:
        op.add_column('projects', Column('options', Text(), nullable=True))
    except Exception as e:
        print(e)
    
    # Set default value for existing projects
    try:
        op.execute(text("UPDATE projects SET options = '{\"logging\": true}' WHERE options IS NULL"))
    except Exception as e:
        print(e)

def downgrade():
    pass