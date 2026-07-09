"""add engine_version to simulations

Revision ID: 0004_engine_version
Revises: 0003_simulation_images
Create Date: 2026-07-06 00:00:00.000000

Adds simulations.engine_version. Existing rows backfill to 1 (legacy allocation +
fixed-posture engine); the new dynamic type-set engine will mark sims as 2.
Portable: Integer + server_default work on Postgres and MySQL alike.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_engine_version"
down_revision: Union[str, None] = "0003_simulation_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulations",
        sa.Column("engine_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("simulations", "engine_version")
