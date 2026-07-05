"""add simulation_images table (per-simulation image slots)

Revision ID: 0003_simulation_images
Revises: 0002_users
Create Date: 2026-07-05 00:00:00.000000

Creates only the `simulation_images` table from its ORM definition (FK to
simulations, unique (simulation_id, name)). Idempotent via checkfirst.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

import app.models  # noqa: F401  -- registers tables on Base.metadata
from app.models import SimulationImage

revision: str = "0003_simulation_images"
down_revision: Union[str, None] = "0002_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    SimulationImage.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    SimulationImage.__table__.drop(bind=bind, checkfirst=True)
