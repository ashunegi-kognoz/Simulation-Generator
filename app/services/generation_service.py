"""Authoring/generation service.

Creates simulations and their generation jobs (idempotently, tenant-scoped), reports
status, and handles review of `[REVIEW]`-flagged decisions. The runner (app/jobs)
does the heavy generation; this service only manages intake and lifecycle rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DecisionRecord,
    GenerationContextRecord,
    GenerationRun,
    Job,
    Participant,
    ReviewAction,
    Simulation,
    SimulationImage,
    SimulationVersion,
    Team,
    Tenant,
)
from app.services.errors import NotFoundError, StateError
from app.schemas.input import SimulationInput
from app.schemas.metadata import SimData


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalars().first()
    if tenant is None:
        raise NotFoundError("unknown tenant")
    return tenant


async def create_simulation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    input_data: dict,
    idempotency_key: str | None = None,
) -> tuple[Simulation, Job]:
    """Validate input and create a Simulation + queued generation Job.

    Idempotent on `idempotency_key` within the tenant: a repeat returns the original
    simulation and job rather than creating duplicates.
    """
    await _require_tenant(session, tenant_id)
    # Validates the authored payload; ValidationError propagates to the API (422).
    si = SimulationInput.model_validate(input_data)
    # Input cap (Part 4 hardening): bound generation cost by limiting round count.
    from app.config import get_settings

    max_rounds = get_settings().max_rounds
    if len(si.rounds) > max_rounds:
        raise StateError(f"at most {max_rounds} rounds are allowed (got {len(si.rounds)})")

    if idempotency_key:
        existing = (
            await session.execute(
                select(Job)
                .join(Simulation, Job.simulation_id == Simulation.id)
                .where(
                    Simulation.tenant_id == tenant_id,
                    Job.idempotency_key == idempotency_key,
                )
                .order_by(Job.created_at)
                .limit(1)
            )
        ).scalars().first()
        if existing is not None:
            sim = (
                await session.execute(
                    select(Simulation).where(Simulation.id == existing.simulation_id)
                )
            ).scalars().one()
            return sim, existing

    sim = Simulation(
        tenant_id=tenant_id,
        name=input_data.get("simulation_name", "Untitled"),
        input_jsonb=input_data,
        engine_version=int(input_data.get("engine_version", 1) or 1),
        status="queued",
    )
    session.add(sim)
    await session.flush()  # assign sim.id

    job = Job(
        simulation_id=sim.id,
        kind="generate",
        status="queued",
        idempotency_key=idempotency_key,
    )
    session.add(job)
    await session.flush()
    return sim, job


async def get_simulation(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> Simulation:
    sim = (
        await session.execute(
            select(Simulation).where(
                Simulation.id == simulation_id, Simulation.tenant_id == tenant_id
            )
        )
    ).scalars().first()
    if sim is None:
        raise NotFoundError("simulation not found")
    return sim


async def latest_version(
    session: AsyncSession, simulation_id: uuid.UUID
) -> SimulationVersion | None:
    return (
        await session.execute(
            select(SimulationVersion)
            .where(SimulationVersion.simulation_id == simulation_id)
            .order_by(SimulationVersion.version.desc())
            .limit(1)
        )
    ).scalars().first()


async def get_status(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> dict:
    sim = await get_simulation(session, tenant_id, simulation_id)
    job = (
        await session.execute(
            select(Job)
            .where(Job.simulation_id == simulation_id)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    version = await latest_version(session, simulation_id)
    flagged = 0
    if version is not None:
        flagged = (
            await session.execute(
                select(func.count())
                .select_from(DecisionRecord)
                .where(
                    DecisionRecord.simulation_version_id == version.id,
                    DecisionRecord.flagged_review.is_(True),
                )
            )
        ).scalar_one()
    return {
        "simulation_id": str(simulation_id),
        "status": sim.status,
        "job_status": job.status if job else None,
        "job_error": job.error if job else None,
        "progress": (job.progress_jsonb or {}) if job else {},
        "needs_review": sim.status == "needs_review",
        "flagged_count": int(flagged),
        "version": version.version if version else None,
    }


async def list_flagged_decisions(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> list[dict]:
    await get_simulation(session, tenant_id, simulation_id)
    version = await latest_version(session, simulation_id)
    if version is None:
        return []
    rows = (
        await session.execute(
            select(DecisionRecord).where(
                DecisionRecord.simulation_version_id == version.id,
                DecisionRecord.flagged_review.is_(True),
            )
        )
    ).scalars().all()
    return [
        {
            "owner_type": r.owner_type,
            "owner_id": r.owner_id,
            "round_index": r.round_index,
            "decision_number": r.decision_number,
            "dimension": r.dimension,
            "decision": r.decision_jsonb,
            "balance_report": r.balance_report_jsonb,
        }
        for r in rows
    ]


async def record_review(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    simulation_id: uuid.UUID,
    reviewer: str,
    action: str,
    notes: str | None = None,
) -> dict:
    if action not in ("approve", "reject"):
        raise StateError("action must be approve or reject")
    sim = await get_simulation(session, tenant_id, simulation_id)
    session.add(
        ReviewAction(simulation_id=sim.id, reviewer=reviewer, action=action, notes=notes)
    )
    if action == "approve":
        sim.status = "ready"
        version = await latest_version(session, simulation_id)
        if version is not None and version.published_at is None:
            from datetime import datetime, timezone

            # Naive UTC to match the TIMESTAMP WITHOUT TIME ZONE column.
            version.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.flush()
    return {"simulation_id": str(simulation_id), "status": sim.status, "action": action}


def _ref_sort_key(ref: str) -> tuple[int, str]:
    """Sort participant refs like p1, p2, ..., p10 numerically (not lexically)."""
    if ref and ref[0] in {"p", "P"} and ref[1:].isdigit():
        return (int(ref[1:]), "")
    return (10**9, ref)


async def list_simulations(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """All simulations for the tenant, newest first, for the dashboard table."""
    sims = (
        await session.execute(
            select(Simulation)
            .where(Simulation.tenant_id == tenant_id)
            .order_by(Simulation.created_at.desc())
        )
    ).scalars().all()
    if not sims:
        return []
    ids = [s.id for s in sims]
    ver_rows = (
        await session.execute(
            select(SimulationVersion.simulation_id, func.max(SimulationVersion.version))
            .where(SimulationVersion.simulation_id.in_(ids))
            .group_by(SimulationVersion.simulation_id)
        )
    ).all()
    latest = {sid: ver for sid, ver in ver_rows}
    out: list[dict] = []
    for s in sims:
        inp = s.input_jsonb or {}
        out.append(
            {
                "id": str(s.id),
                "name": s.name,
                "status": s.status,
                "created_at": s.created_at,
                "participant_count": inp.get("participant_count"),
                "round_count": len(inp.get("rounds", []) or []),
                "version": latest.get(s.id),
            }
        )
    return out


async def get_content(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> dict:
    """The full generated content (facilitator view, postures included)."""
    sim = await get_simulation(session, tenant_id, simulation_id)
    version = await latest_version(session, simulation_id)
    return {
        "simulation_id": str(simulation_id),
        "name": sim.name,
        "status": sim.status,
        "version": version.version if version else None,
        "sim_data": version.sim_data_jsonb if version else None,
    }


def _token_total(usage: object) -> int:
    """generation_runs.tokens is a usage dict; reduce it to a single number."""
    if not isinstance(usage, dict):
        return 0
    total = usage.get("total")
    if isinstance(total, (int, float)):
        return int(total)
    return int(sum(v for v in usage.values() if isinstance(v, (int, float))))


async def get_logs(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> dict:
    """Generation/LLM run records plus the latest job, for the API Logs view."""
    await get_simulation(session, tenant_id, simulation_id)
    job = (
        await session.execute(
            select(Job)
            .where(Job.simulation_id == simulation_id)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    runs = (
        await session.execute(
            select(GenerationRun)
            .where(GenerationRun.simulation_id == simulation_id)
            .order_by(GenerationRun.created_at.asc())
        )
    ).scalars().all()
    return {
        "job": None
        if job is None
        else {
            "id": str(job.id),
            "status": job.status,
            "error": job.error,
            "created_at": job.created_at,
        },
        "runs": [
            {
                "stage": r.stage,
                "model": r.model,
                "prompt_version": r.prompt_version,
                "seed": r.seed,
                "tokens": _token_total(r.tokens),
                "latency_ms": r.latency_ms,
                "created_at": r.created_at,
            }
            for r in runs
        ],
    }


async def get_mapping(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> dict:
    """Participant -> role mapping and team membership (User & Group Mapping)."""
    await get_simulation(session, tenant_id, simulation_id)
    parts = (
        await session.execute(
            select(Participant).where(Participant.simulation_id == simulation_id)
        )
    ).scalars().all()
    parts = sorted(parts, key=lambda p: _ref_sort_key(p.external_ref))
    part_ids = [p.id for p in parts]
    ctx_rows = (
        (
            await session.execute(
                select(GenerationContextRecord).where(
                    GenerationContextRecord.participant_id.in_(part_ids)
                )
            )
        ).scalars().all()
        if part_ids
        else []
    )
    ctx_by_pid = {c.participant_id: (c.context_jsonb or {}) for c in ctx_rows}
    uuid_to_ref = {p.id: p.external_ref for p in parts}

    participants = []
    for p in parts:
        c = ctx_by_pid.get(p.id, {})
        participants.append(
            {
                "ref": p.external_ref,
                "role_title": c.get("role_title"),
                "function": c.get("function"),
                "entity": c.get("entity"),
                "seniority_band": c.get("seniority_band"),
            }
        )

    teams = (
        await session.execute(
            select(Team)
            .where(Team.simulation_id == simulation_id)
            .order_by(Team.round_index, Team.name)
        )
    ).scalars().all()
    team_out = []
    for t in teams:
        member_refs = []
        for pid in t.participant_ids_jsonb or []:
            try:
                key = uuid.UUID(pid) if isinstance(pid, str) else pid
            except (ValueError, TypeError):
                key = pid
            member_refs.append(uuid_to_ref.get(key, str(pid)))
        member_refs.sort(key=_ref_sort_key)
        team_out.append(
            {
                "id": str(t.id),
                "name": t.name,
                "round_index": t.round_index,
                "members": member_refs,
            }
        )

    return {"participants": participants, "teams": team_out}


async def update_content(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    simulation_id: uuid.UUID,
    sim_data_in: dict,
) -> dict:
    """Persist admin edits to the latest generated content.

    Validates the edited content against ``SimData``, overwrites the latest
    version's ``sim_data_jsonb``, and syncs the per-decision ``DecisionRecord``
    rows in place (so the participant runtime, which reads those rows, reflects
    the edits) while preserving each record's balance report and review flag.
    """
    await get_simulation(session, tenant_id, simulation_id)
    version = await latest_version(session, simulation_id)
    if version is None:
        raise NotFoundError("no generated content to edit")

    # Validate: rejects structural corruption (e.g. a decision missing a posture).
    validated = SimData.model_validate(sim_data_in)
    # A team's shared situation is the single source of truth: when present, sync
    # it into every member copy so an admin edit can never leave members stale.
    for rnd in validated.rounds.values():
        for tc in (rnd.teams or {}).values():
            if tc.situation_data:
                for member in tc.members.values():
                    member.situation_data = tc.situation_data
    data = validated.model_dump(mode="json")
    version.sim_data_jsonb = data

    records = (
        await session.execute(
            select(DecisionRecord).where(
                DecisionRecord.simulation_version_id == version.id
            )
        )
    ).scalars().all()
    by_key = {
        (r.owner_type, r.owner_id, r.round_index, r.decision_number): r for r in records
    }

    def _sync(owner_type: str, owner_id: str, round_index: int, board: list[dict]) -> None:
        for d in board or []:
            rec = by_key.get((owner_type, owner_id, round_index, d["decision_number"]))
            if rec is not None:
                rec.decision_jsonb = d
                rec.dimension = d.get("dimension", rec.dimension)

    for round_key, rnd in (data.get("rounds") or {}).items():
        try:
            ridx = int(round_key.replace("round_", ""))
        except (ValueError, AttributeError):
            continue
        for pid, pc in (rnd.get("participants") or {}).items():
            _sync("participant", pid, ridx, pc.get("decision_board", []))
        for _tid, tc in (rnd.get("teams") or {}).items():
            for pid, mc in (tc.get("members") or {}).items():
                _sync("team_member", pid, ridx, mc.get("decision_board", []))

    await session.commit()
    return {
        "simulation_id": str(simulation_id),
        "version": version.version,
        "saved": True,
    }


def _image_out(row: "SimulationImage") -> dict:
    return {
        "name": row.name,
        "url": row.url,
        "content_type": row.content_type,
        "created_at": row.created_at,
    }


async def list_simulation_images(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID
) -> list[dict]:
    await get_simulation(session, tenant_id, simulation_id)
    rows = (
        await session.execute(
            select(SimulationImage)
            .where(SimulationImage.simulation_id == simulation_id)
            .order_by(SimulationImage.created_at.asc())
        )
    ).scalars().all()
    return [_image_out(r) for r in rows]


async def add_simulation_image(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    simulation_id: uuid.UUID,
    name: str,
    data_uri: str,
) -> dict:
    """Upload an image to Cloudinary and store its URL under `name` (upsert by name)."""
    from app.services import cloudinary_service

    await get_simulation(session, tenant_id, simulation_id)
    name = (name or "").strip()
    if not name:
        raise StateError("An image name is required.")
    if not (data_uri or "").strip():
        raise StateError("No image data was provided.")

    result = await cloudinary_service.upload_image(
        data_uri=data_uri, folder=f"allocation-room/{simulation_id}"
    )

    existing = (
        await session.execute(
            select(SimulationImage).where(
                SimulationImage.simulation_id == simulation_id,
                SimulationImage.name == name,
            )
        )
    ).scalars().first()

    if existing is not None:
        old_public_id = existing.public_id
        existing.url = result["url"]
        existing.public_id = result["public_id"]
        existing.content_type = result.get("content_type") or ""
        await session.commit()
        if old_public_id and old_public_id != result["public_id"]:
            await cloudinary_service.delete_image(old_public_id)
        row = existing
    else:
        row = SimulationImage(
            simulation_id=simulation_id,
            name=name,
            url=result["url"],
            public_id=result["public_id"],
            content_type=result.get("content_type") or "",
        )
        session.add(row)
        await session.commit()
    return _image_out(row)


async def delete_simulation_image(
    session: AsyncSession, tenant_id: uuid.UUID, simulation_id: uuid.UUID, name: str
) -> dict:
    from app.services import cloudinary_service

    await get_simulation(session, tenant_id, simulation_id)
    row = (
        await session.execute(
            select(SimulationImage).where(
                SimulationImage.simulation_id == simulation_id,
                SimulationImage.name == name,
            )
        )
    ).scalars().first()
    if row is None:
        raise NotFoundError("image not found")
    public_id = row.public_id
    await session.delete(row)
    await session.commit()
    if public_id:
        await cloudinary_service.delete_image(public_id)
    return {"deleted": True, "name": name}


# --- Edit inputs & regenerate (revisions) -----------------------------------

# Spec-level fields: a change to any of these invalidates ALL generated content
# (the shared world/teaching frame depends on them), so the revision is a full
# regeneration.
_FULL_REGEN_FIELDS = (
    "business_context",
    "subject_matter",
    "company_name",
    "simulation_type",
    "locale",
    "seed",
    "engine_version",
    "rounds",
)


def _diff_scope(old_input: dict, new_input: dict) -> tuple[str, list[str], list[str]]:
    """Classify a revision: ('full', [], []) or ('partial', participant_ids, team_ids).

    Partial scope is computed at the NORMALIZED participant level: a participant is
    invalidated iff the generation context it would receive (role identity + role
    brief + KPIs + rounds) differs between old and new input. This is precise under
    role edits, additions, and removals (round-robin shifts included). Teams are
    invalidated iff they contain an invalidated member.
    """
    from app.pipeline import IntakeNormalizer
    from app.schemas.input import SimulationInput

    for field in _FULL_REGEN_FIELDS:
        if old_input.get(field) != new_input.get(field):
            return "full", [], []

    normalizer = IntakeNormalizer()
    old_spec = normalizer.normalize(SimulationInput.model_validate(old_input))
    new_spec = normalizer.normalize(SimulationInput.model_validate(new_input))

    old_ctx = {p.participant_id: p.context.model_dump_json() for p in old_spec.participants}
    changed: list[str] = []
    for p in new_spec.participants:
        if old_ctx.get(p.participant_id) != p.context.model_dump_json():
            changed.append(p.participant_id)

    changed_set = set(changed)
    team_ids = [
        t.team_id
        for t in new_spec.teams
        if any(m.participant_id in changed_set for m in t.members)
    ]
    return "partial", changed, team_ids


async def revise_simulation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    simulation_id: uuid.UUID,
    new_input: dict,
) -> tuple[Simulation, Job, dict]:
    """Apply edited inputs and queue a dependency-aware regeneration.

    Only content whose inputs actually changed is regenerated: role-level edits
    invalidate just those participants (and teams containing them); shared
    world/context/frame and all untouched participants are reused via their
    checkpoints. A change to any spec-level field regenerates everything. Either
    way the run produces the NEXT SimulationVersion; prior versions stay intact.
    """
    from sqlalchemy import delete as sa_delete

    from app.models import GenerationRun
    from app.schemas.input import SimulationInput

    sim = await get_simulation(session, tenant_id, simulation_id)
    if sim.status in ("queued", "generating"):
        raise StateError("a generation job is already queued or running for this simulation")

    old_input = dict(sim.input_jsonb or {})
    # Keep identity fields authoritative from the stored simulation.
    new_input = dict(new_input)
    new_input["tenant_id"] = old_input.get("tenant_id", str(tenant_id))
    SimulationInput.model_validate(new_input)  # reject malformed edits up front

    scope, participant_ids, team_ids = _diff_scope(old_input, new_input)

    if scope == "full":
        await session.execute(
            sa_delete(GenerationRun).where(
                GenerationRun.simulation_id == sim.id,
                GenerationRun.stage.like("ckpt:%"),
            )
        )
    else:
        stale = [f"ckpt:participant:{pid}" for pid in participant_ids] + [
            f"ckpt:team:{tid}" for tid in team_ids
        ]
        if stale:
            await session.execute(
                sa_delete(GenerationRun).where(
                    GenerationRun.simulation_id == sim.id,
                    GenerationRun.stage.in_(stale),
                )
            )

    sim.input_jsonb = new_input
    sim.name = new_input.get("simulation_name", sim.name)
    sim.engine_version = int(new_input.get("engine_version", sim.engine_version) or 1)
    sim.status = "queued"

    job = Job(simulation_id=sim.id, kind="generate", status="queued")
    session.add(job)
    await session.flush()

    info = {
        "scope": scope,
        "regenerating_participants": participant_ids,
        "regenerating_teams": team_ids,
    }
    return sim, job, info
