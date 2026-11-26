"""Make audience, geography, time_horizon optional and add additional_context.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("projects", "audience", nullable=True)
    op.alter_column("projects", "geography", nullable=True)
    op.alter_column("projects", "time_horizon", nullable=True)
    op.add_column("projects", sa.Column("additional_context", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "additional_context")
    op.alter_column("projects", "time_horizon", nullable=False)
    op.alter_column("projects", "geography", nullable=False)
    op.alter_column("projects", "audience", nullable=False)
