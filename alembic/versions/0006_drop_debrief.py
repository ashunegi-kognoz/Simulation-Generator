"""Drop the debriefs table.

The LLM-written debrief is fully retired: the Reflection Board (deterministic,
allocation-driven) replaced it, and all debrief code has been removed. Dropping
the storage table completes the removal. Downgrade recreates the empty shell.

Revision ID: 0006_drop_debrief
Revises: 0005_dimension_width
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_drop_debrief"
down_revision: Union[str, None] = "0005_dimension_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS debriefs")


def downgrade() -> None:
    op.create_table(
        "debriefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False, index=True),
        sa.Column("debrief_jsonb", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
