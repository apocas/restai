from sqlalchemy import text, Column, Text
from alembic import op

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add options column to projects table
    op.add_column('projects', Column('options', Text(), nullable=True))
    
    # Set default value for existing projects
    op.execute(text("UPDATE projects SET options = '{\"logging\": true}' WHERE options IS NULL"))

def downgrade():
    # Remove options column from projects table
    op.drop_column('projects', 'options') 