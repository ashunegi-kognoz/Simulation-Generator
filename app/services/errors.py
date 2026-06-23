"""Service-layer exceptions, mapped to HTTP status codes in the API layer."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for service errors."""


class NotFoundError(ServiceError):
    """Requested entity does not exist (or is not visible to this tenant)."""


class ConflictError(ServiceError):
    """The request conflicts with current state."""


class StateError(ServiceError):
    """The entity is not in a state that permits this operation."""
