from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Table
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None

def upgrade():
    # Create teams table
    try:
        op.create_table(
            'teams',
            Column('id', Integer, primary_key=True, index=True),
            Column('name', String(255), unique=True, index=True),
            Column('description', Text),
            Column('created_at', DateTime, default=datetime.utcnow),
            Column('updated_at', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
            Column('creator_id', Integer, ForeignKey('users.id'), nullable=True)
        )
    except Exception as e:
        print(f"Error creating teams table: {e}")

    # Create teams_users relationship table
    try:
        op.create_table(
            'teams_users',
            Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True),
            Column('user_id', Integer, ForeignKey('users.id'), primary_key=True)
        )
    except Exception as e:
        print(f"Error creating teams_users table: {e}")
    
    # Create teams_admins relationship table
    try:
        op.create_table(
            'teams_admins',
            Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True),
            Column('user_id', Integer, ForeignKey('users.id'), primary_key=True)
        )
    except Exception as e:
        print(f"Error creating teams_admins table: {e}")
    
    # Create teams_projects relationship table
    try:
        op.create_table(
            'teams_projects',
            Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True),
            Column('project_id', Integer, ForeignKey('projects.id'), primary_key=True)
        )
    except Exception as e:
        print(f"Error creating teams_projects table: {e}")
    
    # Create teams_llms relationship table
    try:
        op.create_table(
            'teams_llms',
            Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True),
            Column('llm_id', Integer, ForeignKey('llms.id'), primary_key=True)
        )
    except Exception as e:
        print(f"Error creating teams_llms table: {e}")
    
    # Create teams_embeddings relationship table
    try:
        op.create_table(
            'teams_embeddings',
            Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True),
            Column('embedding_id', Integer, ForeignKey('embeddings.id'), primary_key=True)
        )
    except Exception as e:
        print(f"Error creating teams_embeddings table: {e}")

def downgrade():
    # Drop relationship tables first (to avoid foreign key constraints)
    try:
        op.drop_table('teams_embeddings')
    except Exception as e:
        print(f"Error dropping teams_embeddings table: {e}")
    
    try:
        op.drop_table('teams_llms')
    except Exception as e:
        print(f"Error dropping teams_llms table: {e}")
    
    try:
        op.drop_table('teams_projects')
    except Exception as e:
        print(f"Error dropping teams_projects table: {e}")
    
    try:
        op.drop_table('teams_admins')
    except Exception as e:
        print(f"Error dropping teams_admins table: {e}")
    
    try:
        op.drop_table('teams_users')
    except Exception as e:
        print(f"Error dropping teams_users table: {e}")
    
    # Drop teams table last
    try:
        op.drop_table('teams')
    except Exception as e:
        print(f"Error dropping teams table: {e}")