from alembic import op
import sqlalchemy as sa

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'kg_entities',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('normalized', sa.String(255), nullable=False, index=True),
            sa.Column('entity_type', sa.String(50), nullable=False),
            sa.Column('mention_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('project_id', 'normalized', 'entity_type', name='uq_kg_entities_project_norm_type'),
        )
    except Exception as e:
        print(f"Error creating kg_entities: {e}")

    try:
        op.create_table(
            'kg_entity_mentions',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('entity_id', sa.Integer(), sa.ForeignKey('kg_entities.id'), nullable=False, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('source', sa.String(500), nullable=False, index=True),
            sa.Column('mention_count', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('entity_id', 'source', name='uq_kg_mentions_entity_source'),
        )
    except Exception as e:
        print(f"Error creating kg_entity_mentions: {e}")

    try:
        op.create_table(
            'kg_entity_relationships',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False, index=True),
            sa.Column('from_entity_id', sa.Integer(), sa.ForeignKey('kg_entities.id'), nullable=False),
            sa.Column('to_entity_id', sa.Integer(), sa.ForeignKey('kg_entities.id'), nullable=False),
            sa.Column('weight', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.UniqueConstraint('project_id', 'from_entity_id', 'to_entity_id', name='uq_kg_rel_project_from_to'),
        )
    except Exception as e:
        print(f"Error creating kg_entity_relationships: {e}")


def downgrade():
    for table in ('kg_entity_relationships', 'kg_entity_mentions', 'kg_entities'):
        try:
            op.drop_table(table)
        except Exception as e:
            print(f"Error dropping {table}: {e}")
