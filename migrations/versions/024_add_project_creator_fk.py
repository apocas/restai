from alembic import op
import sqlalchemy as sa

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None

def upgrade():
    try:
        # Null out orphaned creator values that reference deleted users
        conn = op.get_bind()
        conn.execute(sa.text(
            "UPDATE projects SET creator = NULL WHERE creator IS NOT NULL AND creator NOT IN (SELECT id FROM users)"
        ))
        # Add foreign key constraint
        with op.batch_alter_table("projects") as batch_op:
            batch_op.create_foreign_key("fk_projects_creator_users", "users", ["creator"], ["id"])
    except Exception as e:
        print(f"Error adding creator FK: {e}")

def downgrade():
    try:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_constraint("fk_projects_creator_users", type_="foreignkey")
    except Exception as e:
        print(f"Error dropping creator FK: {e}")
