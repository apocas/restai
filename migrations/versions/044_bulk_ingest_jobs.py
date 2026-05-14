"""Bulk file ingest queue for RAG projects (consumed by crons/bulk_ingest.py)."""
import sqlalchemy as sa
from alembic import op


revision = '044'
down_revision = '043'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.create_table(
            'bulk_ingest_jobs',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('filename', sa.String(512), nullable=False),
            sa.Column('mime_type', sa.String(255), nullable=True),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('file_path', sa.String(1024), nullable=False),
            sa.Column('method', sa.String(32), nullable=True),
            sa.Column('splitter', sa.String(32), nullable=True, server_default='sentence'),
            sa.Column('chunks', sa.Integer(), nullable=True, server_default='256'),
            sa.Column('status', sa.String(16), nullable=False, server_default='queued', index=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('documents_count', sa.Integer(), nullable=True),
            sa.Column('chunks_count', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
        )
    except Exception:
        pass


def downgrade():
    try:
        op.drop_table('bulk_ingest_jobs')
    except Exception:
        pass
