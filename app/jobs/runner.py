"""In-process async job runner (Section 8 / Phase 7).

No Celery, no Redis. A queued `jobs` row is claimed with `SELECT ... FOR UPDATE SKIP
LOCKED` (PostgreSQL) so multiple workers never grab the same job; on SQLite (tests)
the claim degrades to a guarded update. Processing normalizes the input, persists the
de-identified participants/teams, runs the Part 2 generation engine through a
`DbCheckpointer`, then writes the immutable `SimulationVersion`, the per-decision
`DecisionRecord`s (with balance reports + review flags), and a `generation_runs`
audit row. Status transitions are recorded on both the job and the simulation.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.jobs.checkpointer import DbCheckpointer
from app.llm import get_provider
from app.llm.provider import LLMProvider
from app.models import (
    DecisionRecord,
    GenerationContextRecord,
    GenerationRun,
    Job,
    Participant,
    Simulation,
    SimulationVersion,
    Team,
)
from app.pipeline import IntakeNormalizer, generate_with_audit
from app.pipeline.normalize import CanonicalSpec
from app.schemas.input import SimulationInput
from app.schemas.metadata import SimulationOutput


def _dialect_name() -> str:
    return get_engine().sync_engine.dialect.name


async def claim_job(session: AsyncSession) -> Job | None:
    """Claim one queued job. Uses SKIP LOCKED on PostgreSQL."""
    stmt = select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
    if _dialect_name() == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = (await session.execute(stmt)).scalars().first()
    if job is None:
        return None
    job.status = "running"
    await session.flush()
    return job


async def _persist_normalized(
    session: AsyncSession, sim: Simulation, spec: CanonicalSpec
) -> dict[str, uuid.UUID]:
    """Create de-identified Participant + GenerationContext rows and Team rows.

    Parents (participants) are flushed *before* their child rows (generation
    contexts) are added. These models declare foreign keys but no ORM
    relationships, so SQLAlchemy will not otherwise guarantee parent-before-child
    insert ordering within a single flush — which fails under PostgreSQL's foreign
    key enforcement (it is silently tolerated on SQLite).

    Returns a map of canonical participant_id (e.g. "p1") -> Participant UUID.
    """
    pid_map: dict[str, uuid.UUID] = {}
    contexts: dict[str, Any] = {}
    for p in spec.participants:
        contexts[p.participant_id] = p.context
    for t in spec.teams:
        for member in t.members:
            contexts.setdefault(member.participant_id, member.context)

    # 1) parents: participants
    for canonical_pid in contexts:
        participant_uuid = uuid.uuid4()  # explicit id: known without a flush
        pid_map[canonical_pid] = participant_uuid
        session.add(
            Participant(
                id=participant_uuid,
                tenant_id=sim.tenant_id,
                simulation_id=sim.id,
                external_ref=canonical_pid,
                pii_jsonb={},
            )
        )
    await session.flush()  # participants exist before anything references them

    # 2) children: generation contexts (FK -> participants) and teams
    for canonical_pid, ctx in contexts.items():
        session.add(
            GenerationContextRecord(
                participant_id=pid_map[canonical_pid], context_jsonb=ctx.model_dump()
            )
        )
    for t in spec.teams:
        session.add(
            Team(
                id=uuid.uuid4(),
                simulation_id=sim.id,
                round_index=t.round_index,
                name=t.team_name,
                participant_ids_jsonb=[str(pid_map[pid]) for pid in t.participant_ids],
            )
        )
    await session.flush()
    return pid_map


def _reports_index(checkpoint: DbCheckpointer) -> dict[tuple[str, int, int], tuple[dict | None, bool]]:
    """Map (owner_id, round_index, decision_number) -> (balance_report, flagged)."""
    from app.pipeline.assemble import ParticipantBuildResult, TeamBuildResult

    index: dict[tuple[str, int, int], tuple[dict | None, bool]] = {}
    for node, value in checkpoint._cache.items():  # noqa: SLF001 - internal bridge
        if isinstance(value, ParticipantBuildResult):
            for idx, rc in value.rounds.items():
                for d, rep, fl in zip(rc.decision_board, rc.reports, rc.flagged):
                    index[(value.participant_id, idx, d.decision_number)] = (rep.model_dump(), fl)
        elif isinstance(value, TeamBuildResult):
            for pid, mc in value.members.items():
                for d, rep, fl in zip(mc.decision_board, mc.reports, mc.flagged):
                    index[(pid, value.round_index, d.decision_number)] = (rep.model_dump(), fl)
    return index


def _persist_decisions(
    session: AsyncSession,
    version: SimulationVersion,
    sim_out: SimulationOutput,
    reports: dict[tuple[str, int, int], tuple[dict | None, bool]],
) -> None:
    for round_key, rnd in sim_out.sim_data.rounds.items():
        round_index = int(round_key.split("_")[1])
        if rnd.participants:
            for pid, pc in rnd.participants.items():
                for d in pc.decision_board:
                    rep, flagged = reports.get((pid, round_index, d.decision_number), (None, False))
                    session.add(
                        DecisionRecord(
                            simulation_version_id=version.id,
                            owner_type="participant",
                            owner_id=pid,
                            round_index=round_index,
                            decision_number=d.decision_number,
                            dimension=d.dimension,
                            decision_jsonb=d.model_dump(),
                            balance_report_jsonb=rep,
                            flagged_review=flagged,
                        )
                    )
        if rnd.teams:
            for tc in rnd.teams.values():
                for pid, m in tc.members.items():
                    for d in m.decision_board:
                        rep, flagged = reports.get((pid, round_index, d.decision_number), (None, False))
                        session.add(
                            DecisionRecord(
                                simulation_version_id=version.id,
                                owner_type="team_member",
                                owner_id=pid,
                                round_index=round_index,
                                decision_number=d.decision_number,
                                dimension=d.dimension,
                                decision_jsonb=d.model_dump(),
                                balance_report_jsonb=rep,
                                flagged_review=flagged,
                            )
                        )


async def process_job(session: AsyncSession, job: Job, provider: LLMProvider) -> None:
    settings = get_settings()
    # Capture identifiers up front: after a rollback the ORM objects are expired,
    # and touching their attributes would trigger async IO in a sync context.
    job_id = job.id
    sim = (
        await session.execute(select(Simulation).where(Simulation.id == job.simulation_id))
    ).scalars().one()
    sim_id = sim.id
    sim.status = "generating"
    await session.flush()

    try:
        si = SimulationInput.model_validate(sim.input_jsonb)
        spec = IntakeNormalizer().normalize(si)
        await _persist_normalized(session, sim, spec)

        checkpoint = DbCheckpointer(sim.id)
        await checkpoint.hydrate(session)
        # Important for hosted Postgres poolers (e.g. Neon/Render):
        # release the DB connection before long-running LLM generation so an
        # idle checked-out connection is not closed mid-job.
        await session.commit()

        async def _progress(done: int, total: int, label: str) -> None:
            # Persist visible progress AND stream completed checkpoints, in one
            # short transaction. This is what turns a crash at participant N into
            # a resume at N (hydrate skips persisted nodes) instead of a restart,
            # and lets the status endpoint show "participants 12/50".
            #
            # BEST-EFFORT: a keepalive blip on hosted Postgres must never kill a
            # long generation. On failure we roll back, restore the checkpoint
            # dirty-set (so those nodes persist with the final flush), and let
            # generation continue.
            pending = set(checkpoint._dirty)
            try:
                job_row = await session.get(Job, job_id)
                if job_row is not None:
                    job_row.progress_jsonb = {"done": done, "total": total, "stage": label}
                await checkpoint.flush(session)
                await session.commit()
            except Exception:  # noqa: BLE001 - progress is auxiliary by design
                try:
                    await session.rollback()
                except Exception:  # noqa: BLE001
                    pass
                checkpoint._dirty |= pending

        sim_out, audit = await generate_with_audit(
            spec, provider, checkpoint, engine_version=sim.engine_version,
            progress_cb=_progress,
        )
        await checkpoint.flush(session)

        needs_review = audit.needs_review
        # Revisions: each successful run produces the next version number; the
        # first run is 1, an edit-and-regenerate run becomes 2, and so on. Old
        # versions are immutable and stay readable (sessions pin to the version
        # they played).
        prev = (
            await session.execute(
                select(func.max(SimulationVersion.version)).where(
                    SimulationVersion.simulation_id == sim.id
                )
            )
        ).scalar()
        version = SimulationVersion(
            simulation_id=sim.id,
            version=int(prev or 0) + 1,
            sim_data_jsonb=sim_out.sim_data.model_dump(),
            metadata_jsonb=sim_out.generation_metadata.model_dump(),
            published_at=None if needs_review else _now(),
        )
        session.add(version)
        await session.flush()  # assign version.id

        _persist_decisions(session, version, sim_out, _reports_index(checkpoint))

        session.add(
            GenerationRun(
                simulation_id=sim.id,
                stage="generate",
                prompt_version=None,
                model=settings.llm_model_strong,
                seed=spec.seed,
                input_hash=spec.input_hash,
                tokens=sim_out.generation_metadata.token_usage,
                output_jsonb={
                    "needs_review": needs_review,
                    "flagged_decisions": audit.flagged_decisions,
                    "sanitize_flags": audit.sanitize_flags,
                },
            )
        )

        sim.status = "needs_review" if needs_review else "ready"
        job.status = "completed"
        job.progress_jsonb = {"phase": "done", "needs_review": needs_review}
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - record failure, never crash the worker
        await session.rollback()
        await _mark_failed(session, job_id, sim_id, str(exc))
        # Do not re-raise: the job is marked failed and the caller reports status
        # (the API returns a "failed" status rather than a 500).


async def _mark_failed(
    session: AsyncSession, job_id: uuid.UUID, sim_id: uuid.UUID, error: str
) -> None:
    job = (await session.execute(select(Job).where(Job.id == job_id))).scalars().one()
    sim = (await session.execute(select(Simulation).where(Simulation.id == sim_id))).scalars().one()
    job.status = "failed"
    job.error = error[:2000]
    sim.status = "failed"
    await session.commit()


def _now():
    from datetime import datetime, timezone

    # Naive UTC: the timestamp columns are TIMESTAMP WITHOUT TIME ZONE (like
    # created_at), and asyncpg rejects timezone-aware values for those columns.
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def run_pending(
    session: AsyncSession, provider: LLMProvider | None = None, max_jobs: int = 100
) -> int:
    """Process queued jobs until none remain (or max_jobs hit). Returns count handled."""
    provider = provider or get_provider()
    handled = 0
    while handled < max_jobs:
        job = await claim_job(session)
        if job is None:
            break
        await session.commit()  # persist the running claim before heavy work
        await process_job(session, job, provider)
        handled += 1
    return handled


# --------------------------------------------------------------------------- #
# background worker (production only; gated off in tests)
# --------------------------------------------------------------------------- #
async def worker_loop(poll_seconds: float = 1.0) -> None:
    """Long-running loop that drains queued jobs. Started from the app lifespan in
    non-test environments; cancelled cleanly on shutdown."""
    sessionmaker = get_sessionmaker()
    provider = get_provider()
    while True:
        try:
            async with sessionmaker() as session:
                handled = await run_pending(session, provider)
            if handled == 0:
                await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - keep the loop alive across transient errors
            await asyncio.sleep(poll_seconds)
