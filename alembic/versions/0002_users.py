"""add users table (email/password auth)

Revision ID: 0002_users
Revises: 0001_initial
Create Date: 2026-06-22 00:00:00.000000

Creates only the `users` table from its ORM definition, so the DDL can't drift
from the model (FK to tenants, unique/indexed email). Idempotent via checkfirst.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

import app.models  # noqa: F401  -- registers tables on Base.metadata
from app.models import User

revision: str = "0002_users"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    User.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    User.__table__.drop(bind=bind, checkfirst=True)
