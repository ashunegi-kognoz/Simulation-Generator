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
from typing import Awaitable, TypeVar

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
from app.pipeline.decisions import build_decisions
from app.pipeline.normalize import CanonicalSpec, Checkpointer, InMemoryCheckpointer, ParticipantSpec, TeamSpec
from app.pipeline.reduce import consistency_auditor, editorial_gate, safety_gate
from app.pipeline.roles import role_smith
from app.pipeline.teams import member_situation, team_scenario
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


def _context_blob(bible: NarrativeBible, role_data: str, situation: str, ctx_json: str) -> str:
    # Stable prefix (bible) first; variable role/situation/context last.
    return (
        f"{bible_json(bible)}\n\n=== ROLE ===\n{role_data}\n=== SITUATION ===\n{situation}\n"
        f"=== CONTEXT ===\n{ctx_json}"
    )


async def generate_with_audit(
    spec: CanonicalSpec,
    llm: LLMProvider,
    checkpoint: Checkpointer | None = None,
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
        common = await common_content(spec, bible, llm)
        cp.save("common", common)

    # --- Tier 2: Fan-out ---
    async def build_participant(p: ParticipantSpec) -> ParticipantBuildResult:
        node = f"participant:{p.participant_id}"
        if cp.has(node):
            return cp.load(node)
        role_sit = await role_smith(p.context, bible, llm)
        ctx_json = p.context.model_dump_json()
        rounds: dict[int, RoundParticipantContent] = {}
        for rp in p.individual_rounds:
            blob = _context_blob(bible, role_sit.role_data, role_sit.situation_data, ctx_json)
            build = await build_decisions(blob, rp.dimensions, llm)
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
        team_blob = _context_blob(bible, "team cluster", scenario, team_ctx_json)
        team_build = await build_decisions(team_blob, t.dimensions, llm)
        members: dict[str, MemberBuildContent] = {}
        for member in t.members:
            situation = await member_situation(member.context, scenario, bible, llm)
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
            participant_ids=t.participant_ids,
            members=members,
        )
        cp.save(node, result)
        return result

    sem = asyncio.Semaphore(settings.max_concurrency)
    tasks: list[Awaitable[BuildResult]] = [
        guarded(sem, build_participant(p)) for p in spec.participants
    ] + [guarded(sem, build_team(t)) for t in spec.teams]
    results: list[BuildResult] = list(await asyncio.gather(*tasks))

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
) -> SimulationOutput:
    """Public entry point matching the Section 8.5 signature."""
    sim, _ = await generate_with_audit(spec, llm, checkpoint)
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
