from sqlalchemy import text, Column, Text
from alembic import op

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.add_column('users', Column('options', Text(), nullable=True))
    except Exception as e:
        print(e)

    try:
        op.execute(text("UPDATE users SET options = '{\"credit\": -1.0}' WHERE options IS NULL"))
    except Exception as e:
        print(e)

def downgrade():
    pass