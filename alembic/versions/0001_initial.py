"""initial schema: create all tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00.000000

DECISION: the first migration creates every table directly from the declarative
metadata (`Base.metadata.create_all`). This guarantees the initial schema matches
the ORM models exactly with no hand-maintained DDL to drift. Subsequent schema
changes should be produced with `alembic revision --autogenerate` as normal diffs.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

import app.models  # noqa: F401  -- registers tables on Base.metadata
from app.db import Base

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
