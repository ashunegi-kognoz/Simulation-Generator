"""Widen decisions.dimension for derived focus tags.

Engine-v2 derives each decision's focus from the teaching frame (e.g.
"COMMERCIAL MIX"), replacing the fixed MOVE/HOLD/FRAME set the original
VARCHAR(8) was sized for. Widen to 64 so any 1-3 word tag fits. Legacy rows
are unaffected (widening is lossless and instant).

Revision ID: 0005_dimension_width
Revises: 0004_engine_version
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_dimension_width"
down_revision: Union[str, None] = "0004_engine_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "decisions",
        "dimension",
        existing_type=sa.String(8),
        type_=sa.String(64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "decisions",
        "dimension",
        existing_type=sa.String(64),
        type_=sa.String(8),
        existing_nullable=False,
    )
