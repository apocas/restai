from sqlalchemy import text, Column, Text
from alembic import op

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('projects', Column('options', Text(), nullable=True))
    except Exception as e:
        print(e)

    try:
        op.execute(text("UPDATE projects SET options = '{\"logging\": true}' WHERE options IS NULL"))
    except Exception as e:
        print(e)

def downgrade():
    pass