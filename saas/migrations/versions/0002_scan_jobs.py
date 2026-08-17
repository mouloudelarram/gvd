"""scan_jobs table (durable job state)

Revision ID: 0002_scan_jobs
Revises: 0001_initial
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_scan_jobs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_login", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("job_type", sa.String(length=20), nullable=False, server_default="bulk"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=True),
        sa.Column("total_repositories", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scanned_repositories", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_repositories", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scan_jobs_owner_login", "scan_jobs", ["owner_login"])
    op.create_index("ix_scan_jobs_status", "scan_jobs", ["status"])
    op.create_index("ix_scan_jobs_idempotency_key", "scan_jobs", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_scan_jobs_idempotency_key", table_name="scan_jobs")
    op.drop_index("ix_scan_jobs_status", table_name="scan_jobs")
    op.drop_index("ix_scan_jobs_owner_login", table_name="scan_jobs")
    op.drop_table("scan_jobs")
