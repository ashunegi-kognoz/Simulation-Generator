"""SQLAlchemy ORM models for every entity in Section 14b.

Conventions:
- UUID primary keys (app-side default = uuid4).
- JSONB for generated/structured payloads (Postgres).
- `created_at` / `updated_at` use server-side now().
- Status/enum-ish fields are stored as plain strings; allowed values are
  documented in the brief and enforced in the service layer (Part 3).

ORM classes whose names would collide with Pydantic schema names get a DB-flavored
suffix (e.g. `DecisionRecord`) so re-exports stay unambiguous. `__tablename__`
matches the brief verbatim.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func
from app.models._types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_jsonb: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Simulation(Base):
    __tablename__ = "simulations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    input_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # status in: queued | generating | needs_review | ready | failed
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class SimulationVersion(Base):
    __tablename__ = "simulation_versions"  # immutable
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    sim_data_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metadata_jsonb: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class BibleRecord(Base):
    __tablename__ = "narrative_bibles"
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    bible_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Participant(Base):
    __tablename__ = "participants"  # PII isolated here
    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pii_jsonb: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class GenerationContextRecord(Base):
    __tablename__ = "generation_contexts"  # de-identified; used in prompts
    id: Mapped[uuid.UUID] = _uuid_pk()
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False, index=True
    )
    context_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    participant_ids_jsonb: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class DecisionRecord(Base):
    __tablename__ = "decisions"  # decision_jsonb is canonical (posture-tagged)
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_versions.id"), nullable=False, index=True
    )
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)  # participant | team_member
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension: Mapped[str] = mapped_column(String(8), nullable=False)
    decision_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    balance_report_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    flagged_review: Mapped[bool] = mapped_column(default=False, nullable=False)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_versions.id"), nullable=False, index=True
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False, index=True
    )
    display_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    # status in: active | completed
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class AllocationRecord(Base):
    __tablename__ = "allocations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    units_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # individual | pre | team
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ReflectionRecord(Base):
    __tablename__ = "reflections"
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    decision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reflection_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)


class CommitmentRecord(Base):
    __tablename__ = "commitments"
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    commitment_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)


class FingerprintRecord(Base):
    __tablename__ = "posture_fingerprints"
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    fingerprint_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)


class GroupAnalyticsRecord(Base):
    __tablename__ = "group_analytics"
    id: Mapped[uuid.UUID] = _uuid_pk()
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False, index=True
    )
    analytics_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)


class DebriefRecord(Base):
    __tablename__ = "debriefs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True
    )
    debrief_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)


class GenerationRun(Base):
    __tablename__ = "generation_runs"  # append-only audit log
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_jsonb: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # approve | reject
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # generate | regenerate
    # status in: queued | running | completed | failed
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    progress_jsonb: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # idempotency: nullable, unique per (tenant via simulation) create request
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )


__all__ = [
    "Tenant",
    "Simulation",
    "SimulationVersion",
    "BibleRecord",
    "Participant",
    "GenerationContextRecord",
    "Team",
    "DecisionRecord",
    "Session",
    "AllocationRecord",
    "ReflectionRecord",
    "CommitmentRecord",
    "FingerprintRecord",
    "GroupAnalyticsRecord",
    "DebriefRecord",
    "GenerationRun",
    "ReviewAction",
    "Job",
]
