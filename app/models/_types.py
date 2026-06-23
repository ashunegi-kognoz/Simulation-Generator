"""Portable column types (Part 3 compatibility shim).

Part 1's models target PostgreSQL (JSONB + native UUID). The brief also requires
the platform to run end-to-end offline, and the offline test database is SQLite,
which has neither type. These `TypeDecorator`s keep the *production* behavior
identical (they map to `postgresql.JSONB` and `postgresql.UUID` on Postgres) while
transparently degrading to `JSON` and `CHAR(36)` on SQLite for tests.

They deliberately keep the names `JSONB` and `UUID` and accept the same call
signature (`UUID(as_uuid=True)`) so `app/models/__init__.py` changes by exactly one
import line.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.types import CHAR, JSON, TypeDecorator


class JSONB(TypeDecorator):
    """JSONB on PostgreSQL, JSON elsewhere. Usable as a bare type (``mapped_column(JSONB)``)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


class UUID(TypeDecorator):
    """Native UUID on PostgreSQL, CHAR(36) elsewhere. Always yields ``uuid.UUID`` in Python."""

    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid: bool = True, **kwargs: Any) -> None:
        # `as_uuid` is accepted for call-site parity with postgresql.UUID; values are
        # always surfaced as uuid.UUID regardless.
        self.as_uuid = as_uuid
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID

            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
