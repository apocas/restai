"""Per-API-key monthly token quotas.

Adds three columns to ``api_keys``:
* ``token_quota_monthly`` (nullable int) — monthly cap; NULL = unlimited
* ``tokens_used_this_month`` (int, default 0) — rolling counter
* ``quota_reset_at`` (nullable datetime) — first-of-next-month rollover

Lets an SMB mint one key per customer and isolate quota per customer.
Enforced by ``check_api_key_quota`` in ``restai/budget.py`` alongside
the existing project rate limit + team budget checks.
"""
import sqlalchemy as sa
from alembic import op


revision = '042'
down_revision = '041'
branch_labels = None
depends_on = None


def upgrade():
    for col_name, col in (
        ('token_quota_monthly', sa.Column('token_quota_monthly', sa.Integer(), nullable=True)),
        ('tokens_used_this_month', sa.Column('tokens_used_this_month', sa.Integer(), nullable=False, server_default='0')),
        ('quota_reset_at', sa.Column('quota_reset_at', sa.DateTime(), nullable=True)),
    ):
        try:
            op.add_column('api_keys', col)
        except Exception:
            # Column already present (partial re-run) — safe to ignore.
            pass


def downgrade():
    for col_name in ('token_quota_monthly', 'tokens_used_this_month', 'quota_reset_at'):
        try:
            op.drop_column('api_keys', col_name)
        except Exception:
            pass
