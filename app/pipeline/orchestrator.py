"""Generation orchestrator (Section 8.5).

Runs the three tiers: Foundation (bible, common) -> bounded-concurrency Fan-out
(participants + teams) -> deterministic Reduce (assemble, consistency, safety,
shuffle, bind). Each node is checkpointed so a resumed run skips completed work.

`generate_simulation` returns a `SimulationOutput` exactly per the brief's
signature. `generate_with_audit` additionally returns a `GenerationAudit` (revise
counts, `[REVIEW]` flags, contradictions, editorial findings, sanitize flags) for
the service/authoring layer in Part 3 and for tests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

from app.config import get_settings
from app.llm.provider import LLMProvider
from app.pipeline.assemble import (
    BuildResult,
    MemberBuildContent,
    ParticipantBuildResult,
    RoundParticipantContent,
    TeamBuildResult,
    assemble,
    bind_scoring,
    shuffle_positions,
)
from app.pipeline.common import common_content
from app.pipeline.archetypes import generate_archetypes
from app.pipeline.decision_focus import DecisionFocusSet, canonical_cycle, generate_decision_focuses
from app.pipeline.reflection_spec import generate_reflection_spec
from app.schemas.content import CommonData, DynamicStance, TypeSet
from app.pipeline.decisions import build_decisions
from app.pipeline.normalize import CanonicalSpec, Checkpointer, InMemoryCheckpointer, ParticipantSpec, TeamSpec
from app.pipeline.reduce import consistency_auditor, editorial_gate, safety_gate
from app.pipeline.roles import role_smith
from app.pipeline.teams import team_scenario, team_situation
from app.pipeline.world import bible_json, world_architect
from app.schemas.content import NarrativeBible
from app.schemas.metadata import SimulationOutput

T = TypeVar("T")


@dataclass
class GenerationAudit:
    flagged_decisions: list[str] = field(default_factory=list)
    revisions: dict[str, int] = field(default_factory=dict)
    contradictions: list[str] = field(default_factory=list)
    editorial_findings: list[str] = field(default_factory=list)
    sanitize_flags: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.flagged_decisions or self.contradictions or self.editorial_findings)


async def guarded(sem: asyncio.Semaphore, coro: Awaitable[T]) -> T:
    async with sem:
        return await coro


# (done, total, label) -- awaited after each completed wave/team so the caller can
# persist progress and stream checkpoints.
ProgressCallback = Callable[[int, int, str], Awaitable[None]]


def _context_blob(
    bible: NarrativeBible, role_data: str, situation: str, ctx_json: str, shared: str = ""
) -> str:
    # Stable prefix (bible + frozen shared context) first; variable role/situation last.
    prefix = f"{bible_json(bible)}"
    if shared:
        prefix += f"\n\n{shared}"
    return (
        f"{prefix}\n\n=== ROLE ===\n{role_data}\n=== SITUATION ===\n{situation}\n"
        f"=== CONTEXT ===\n{ctx_json}"
    )


def _shared_context(common: CommonData) -> str:
    """Compact frozen shared context every participant/team build is anchored to.

    Generated once (Tier 1), then injected into every per-participant call so all
    40-50 role builds stay consistent with the same facts, priorities, crisis, and
    teaching frame -- without each call re-deriving them.
    """
    parts: list[str] = ["=== FROZEN SHARED CONTEXT (AUTHORITATIVE; DO NOT CONTRADICT) ==="]
    _landscape_text = "\n".join(
        (f"{e.title}: {e.body}" if e.title else e.body) for e in common.business_landscape
    )
    parts.append(f"BUSINESS LANDSCAPE:\n{_landscape_text}")
    pri_lines = []
    for p in common.business_priorities:
        row_txt = "; ".join(f"{r.item}={r.value}" for r in p.table)
        pri_lines.append(f"- {p.title}" + (f" [{row_txt}]" if row_txt else ""))
    parts.append("SHARED PRIORITIES:\n" + "\n".join(pri_lines))
    parts.append(f"CRISIS:\n{common.crisis_data}")
    if common.reflection_spec is not None:
        rs = common.reflection_spec
        params = "; ".join(f"{p.name} ({p.definition})" for p in rs.outcome_parameters)
        parts.append(
            "TEACHING FRAME:\n"
            f"Framework: {rs.framework_name} -- {rs.framework_definition}\n"
            f"Learning tension: {rs.learning_tension}\n"
            f"Outcome parameters: {params}"
        )
    if common.type_set is not None:
        stance_lines = "\n".join(
            f"- {st.key}: {st.label} -- {st.definition}" for st in common.type_set.stances
        )
        parts.append(f"DECISION STANCES:\n{stance_lines}")
    return "\n\n".join(parts)


async def generate_with_audit(
    spec: CanonicalSpec,
    llm: LLMProvider,
    checkpoint: Checkpointer | None = None,
    engine_version: int = 1,
    progress_cb: "ProgressCallback | None" = None,
) -> tuple[SimulationOutput, GenerationAudit]:
    settings = get_settings()
    cp = checkpoint or InMemoryCheckpointer()
    audit = GenerationAudit(sanitize_flags=list(spec.sanitize_flags))

    # --- Tier 1: Foundation ---
    if cp.has("bible"):
        bible = cp.load("bible")
    else:
        bible = await world_architect(spec, llm)
        cp.save("bible", bible)

    if cp.has("common"):
        common = cp.load("common")
    else:
        common = await common_content(
            spec, bible, llm, include_posture_scheme=engine_version < 2
        )
        cp.save("common", common)

    # Engine-v2: derive the per-simulation type-set (learning tension + four dynamic
    # stances) and attach it to common. Its keys drive both decision generation
    # (one option per stance, validated against the keys) and scoring. v1 leaves
    # posture_keys/stances None, so build_decisions keeps the canonical four.
    posture_keys: list[str] | None = None
    stances = None
    if engine_version >= 2:
        # v2 sims never carry the legacy scheme (also covers checkpoints written
        # by older code versions).
        common.posture_scheme = None
        # The teaching frame comes FIRST: framework + outcome parameters, then the
        # type-set is derived from it so the four stances resolve the spec's tension.
        if cp.has("reflection_spec"):
            reflection_spec = cp.load("reflection_spec")
        else:
            reflection_spec = await generate_reflection_spec(
                spec.subject_matter, spec.business_context, llm
            )
            cp.save("reflection_spec", reflection_spec)
        common.reflection_spec = reflection_spec
        # UNIFIED ENGINE: the four decision stances ARE the four outcome
        # parameters. The type-set is constructed deterministically from the
        # reflection spec (no LLM call), so a participant's allocation on an
        # option maps 1:1 to an outcome parameter on the Reflection Board.
        if cp.has("type_set"):
            type_set = cp.load("type_set")
        else:
            type_set = TypeSet(
                inferred_category=reflection_spec.framework_name,
                learning_tension=reflection_spec.learning_tension,
                stances=[
                    DynamicStance(
                        key=param.key, label=param.name, definition=param.definition
                    )
                    for param in reflection_spec.outcome_parameters
                ]
            )
            cp.save("type_set", type_set)
        common.type_set = type_set
        posture_keys = [s.key for s in type_set.stances]
        stances = list(type_set.stances)

        # Business archetypes: 10 leadership patterns over the four parameters,
        # generated NOW (checkpointed) so the Reflection Board is instant later.
        if cp.has("archetypes"):
            archetype_set = cp.load("archetypes")
        else:
            archetype_set = await generate_archetypes(
                spec.subject_matter, spec.business_context, reflection_spec, llm
            )
            cp.save("archetypes", archetype_set)
        common.business_archetypes = archetype_set.archetypes

    # --- Tier 2: Fan-out ---
    async def build_participant(p: ParticipantSpec) -> ParticipantBuildResult:
        node = f"participant:{p.participant_id}"
        if cp.has(node):
            return cp.load(node)
        role_sit = await role_smith(p.context, bible, llm)
        ctx_json = p.context.model_dump_json()
        rounds: dict[int, RoundParticipantContent] = {}
        blob = _context_blob(bible, role_sit.role_data, role_sit.situation_data, ctx_json, shared_ctx)
        for rp in p.individual_rounds:
            dims = await resolve_focuses(
                "ind", rp.index, rp.dimensions, len(rp.dimensions) or rp.decision_count, "individual"
            )
            round_blob = blob
            note = focus_notes.get(f"ind:{rp.index}")
            if note:
                round_blob = f"{blob}\n\n=== DECISION FOCUS GUIDE ===\n{note}"
            build = await build_decisions(round_blob, dims, llm, posture_keys, stances)
            rounds[rp.index] = RoundParticipantContent(
                situation_data=role_sit.situation_data,
                decision_board=build.decisions,
                reports=build.reports,
                flagged=build.flagged,
                revisions=build.revisions,
            )
        result = ParticipantBuildResult(
            participant_id=p.participant_id, role_data=role_sit.role_data, rounds=rounds
        )
        cp.save(node, result)
        return result

    async def build_team(t: TeamSpec) -> TeamBuildResult:
        node = f"team:{t.team_id}"
        if cp.has(node):
            return cp.load(node)
        scenario = await team_scenario(t, bible, llm)
        # ONE decision board for the whole team: every member sees the same board
        # in a group round (postures still hidden until debrief).
        team_ctx_json = t.members[0].context.model_dump_json() if t.members else ""
        team_blob = _context_blob(bible, "team cluster", scenario, team_ctx_json, shared_ctx)
        team_dims = await resolve_focuses(
            "team", t.round_index, t.dimensions, len(t.dimensions) or t.decision_count, "group"
        )
        note = focus_notes.get(f"team:{t.round_index}")
        if note:
            team_blob = f"{team_blob}\n\n=== DECISION FOCUS GUIDE ===\n{note}"
        team_build = await build_decisions(team_blob, team_dims, llm, posture_keys, stances)
        # ONE shared situation for the whole team (identical for every member) --
        # a single call instead of one per member.
        situation = await team_situation(t, scenario, bible, llm)
        members: dict[str, MemberBuildContent] = {}
        for member in t.members:
            members[member.participant_id] = MemberBuildContent(
                situation_data=situation,
                decision_board=team_build.decisions,
                reports=team_build.reports,
                flagged=team_build.flagged,
                revisions=team_build.revisions,
            )
        result = TeamBuildResult(
            team_id=t.team_id,
            team_name=t.team_name,
            round_index=t.round_index,
            scenario_data=scenario,
            situation_data=situation,
            participant_ids=t.participant_ids,
            members=members,
        )
        cp.save(node, result)
        return result

    # Frozen shared context: built ONCE from Tier-1 output, injected into every
    # per-participant/team call so all builds stay consistent with the same facts.
    shared_ctx = _shared_context(common)

    # Decision focuses per round: authored dimensions (legacy) are used verbatim;
    # otherwise v2 DERIVES the focuses from the teaching frame (once per round,
    # checkpointed, shared by every participant for comparability), and v1 falls
    # back to the canonical MOVE/HOLD/FRAME cycle without an LLM call.
    focus_notes: dict[str, str] = {}

    async def resolve_focuses(kind: str, index: int, authored: list[str], count: int, round_type: str) -> list[str]:
        if authored:
            return list(authored)
        if engine_version < 2:
            return canonical_cycle(count)
        node = f"focus:{kind}:r{index}:{count}:{round_type}"
        if cp.has(node):
            stored = cp.load(node)
        else:
            derived = await generate_decision_focuses(
                spec.subject_matter, count, round_type, llm,
                common.reflection_spec, common.type_set,
            )
            stored = DecisionFocusSet(focuses=derived)
            cp.save(node, stored)
        focus_notes[f"{kind}:{index}"] = "\n".join(
            f"- {f.tag}: {f.description}" for f in stored.focuses
        )
        return [f.tag for f in stored.focuses]

    # Batched fan-out: participants are generated in small ordered waves instead of
    # all at once. With 40-50 distinct roles this bounds model load and memory,
    # yields readable progress, and (with the runner's incremental checkpoint
    # flush) makes a crash at participant N resume at N, not zero. The semaphore
    # still caps total in-flight LLM calls.
    # Derive every round's decision focuses ONCE, sequentially, before the
    # concurrent fan-out. Without this, participants in the same wave race the
    # focus checkpoint and can each derive a different set (breaking cross-
    # participant comparability of the by-focus scoring).
    if spec.participants:
        for rp in spec.participants[0].individual_rounds:
            await resolve_focuses(
                "ind", rp.index, rp.dimensions,
                len(rp.dimensions) or rp.decision_count, "individual",
            )
    for t in spec.teams:
        await resolve_focuses(
            "team", t.round_index, t.dimensions,
            len(t.dimensions) or t.decision_count, "group",
        )

    sem = asyncio.Semaphore(settings.max_concurrency)
    total = len(spec.participants) + len(spec.teams)
    done = 0
    results: list[BuildResult] = []

    batch_size = max(1, settings.participant_batch_size)
    for start in range(0, len(spec.participants), batch_size):
        wave = spec.participants[start : start + batch_size]
        wave_results = await asyncio.gather(*(guarded(sem, build_participant(p)) for p in wave))
        results.extend(wave_results)
        done += len(wave)
        if progress_cb is not None:
            await progress_cb(done, total, f"participants {done}/{len(spec.participants)}")

    for t in spec.teams:
        results.append(await guarded(sem, build_team(t)))
        done += 1
        if progress_cb is not None:
            await progress_cb(done, total, f"team {t.team_id}")

    _collect_flags(results, audit)

    # --- Tier 3: Reduce (deterministic) ---
    draft = assemble(spec, bible, common, results)

    contradictions = await consistency_auditor(draft, bible, llm)
    if contradictions:
        # DECISION: one targeted re-audit, then mark needs_review (we never silently
        # edit content). Mock returns [], so this path is inert offline.
        contradictions = await consistency_auditor(draft, bible, llm)
    audit.contradictions = contradictions

    safety_gate(draft)  # raises on any PII leak

    sim = shuffle_positions(draft, seed=spec.seed)
    sim = bind_scoring(sim)

    audit.editorial_findings = editorial_gate(sim)
    return sim, audit


async def generate_simulation(
    spec: CanonicalSpec,
    llm: LLMProvider,
    checkpoint: Checkpointer | None = None,
    engine_version: int = 1,
    progress_cb: ProgressCallback | None = None,
) -> SimulationOutput:
    """Public entry point matching the Section 8.5 signature."""
    sim, _ = await generate_with_audit(spec, llm, checkpoint, engine_version, progress_cb)
    return sim


def _collect_flags(results: list[BuildResult], audit: GenerationAudit) -> None:
    for r in results:
        if isinstance(r, ParticipantBuildResult):
            for idx, rc in r.rounds.items():
                for d, rev, fl in zip(rc.decision_board, rc.revisions, rc.flagged):
                    key = f"{r.participant_id}:r{idx}:d{d.decision_number}"
                    audit.revisions[key] = rev
                    if fl:
                        audit.flagged_decisions.append(key)
        elif isinstance(r, TeamBuildResult):
            for pid, mc in r.members.items():
                for d, rev, fl in zip(mc.decision_board, mc.revisions, mc.flagged):
                    key = f"{r.team_id}:{pid}:d{d.decision_number}"
                    audit.revisions[key] = rev
                    if fl:
                        audit.flagged_decisions.append(key)
