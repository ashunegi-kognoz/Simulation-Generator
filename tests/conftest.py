"""Shared pytest setup.

Kept import-light on purpose: setting environment defaults here means schema tests
run with only pydantic installed, while later parts (pipeline/API) can rely on the
mock provider being the default. We do NOT import app.db / app.models here so the
schema suite has no database dependency.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("MOCK_FORCE_REBALANCE", "0")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/allocation_room_test"
)
