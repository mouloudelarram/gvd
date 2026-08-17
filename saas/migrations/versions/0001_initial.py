"""initial schema: scan_events

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_login", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("scan_date", sa.Date(), nullable=False),
        sa.Column("total_findings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_scan_events_user_login", "scan_events", ["user_login"])
    op.create_index("ix_scan_events_scan_date", "scan_events", ["scan_date"])


def downgrade() -> None:
    op.drop_index("ix_scan_events_scan_date", table_name="scan_events")
    op.drop_index("ix_scan_events_user_login", table_name="scan_events")
    op.drop_table("scan_events")
