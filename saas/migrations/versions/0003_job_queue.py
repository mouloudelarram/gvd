"""scan_jobs: add retry_count and cancel_requested (durable queue)

Revision ID: 0003_job_queue
Revises: 0002_scan_jobs
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_job_queue"
down_revision: Union[str, None] = "0002_scan_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scan_jobs") as batch:
        batch.add_column(
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("scan_jobs") as batch:
        batch.drop_column("cancel_requested")
        batch.drop_column("retry_count")
