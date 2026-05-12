"""add catchall_jobs table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catchall_jobs",
        sa.Column("id", sqlmodel.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.AutoString(), nullable=False),
        sa.Column("job_id", sqlmodel.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.AutoString(), nullable=False, server_default="submitted"),
        sa.Column("query", sqlmodel.AutoString(), nullable=False),
        sa.Column("mode", sqlmodel.AutoString(), nullable=False, server_default="lite"),
        sa.Column("records", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catchall_jobs_user_id", "catchall_jobs", ["user_id"])
    op.create_index("ix_catchall_jobs_job_id", "catchall_jobs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_catchall_jobs_job_id", table_name="catchall_jobs")
    op.drop_index("ix_catchall_jobs_user_id", table_name="catchall_jobs")
    op.drop_table("catchall_jobs")
