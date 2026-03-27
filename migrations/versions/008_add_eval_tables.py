from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

def upgrade():
    try:
        op.create_table(
            'eval_datasets',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('name', sa.String(255)),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )
    except Exception as e:
        print(f"Error creating eval_datasets: {e}")

    try:
        op.create_table(
            'eval_test_cases',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('eval_datasets.id'), nullable=False),
            sa.Column('question', sa.Text(), nullable=False),
            sa.Column('expected_answer', sa.Text(), nullable=True),
            sa.Column('context', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime()),
        )
    except Exception as e:
        print(f"Error creating eval_test_cases: {e}")

    try:
        op.create_table(
            'eval_runs',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('eval_datasets.id'), nullable=False),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=False),
            sa.Column('status', sa.String(50), default='pending'),
            sa.Column('metrics', sa.Text()),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime()),
            sa.Column('error', sa.Text(), nullable=True),
        )
    except Exception as e:
        print(f"Error creating eval_runs: {e}")

    try:
        op.create_table(
            'eval_results',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('run_id', sa.Integer(), sa.ForeignKey('eval_runs.id'), nullable=False),
            sa.Column('test_case_id', sa.Integer(), sa.ForeignKey('eval_test_cases.id'), nullable=False),
            sa.Column('actual_answer', sa.Text(), nullable=True),
            sa.Column('retrieval_context', sa.Text(), nullable=True),
            sa.Column('metric_name', sa.String(255)),
            sa.Column('score', sa.Float()),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('passed', sa.Boolean(), default=False),
            sa.Column('latency_ms', sa.Integer(), nullable=True),
        )
    except Exception as e:
        print(f"Error creating eval_results: {e}")


def downgrade():
    for table in ['eval_results', 'eval_runs', 'eval_test_cases', 'eval_datasets']:
        try:
            op.drop_table(table)
        except Exception as e:
            print(f"Error dropping {table}: {e}")
