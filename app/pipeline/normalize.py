"""Intake normalization (deterministic) and the canonical pipeline spec.

`IntakeNormalizer` turns an authored `SimulationInput` into a `CanonicalSpec`:
de-identified per-participant `GenerationContext`s, individual round plans, and
team partitions for group rounds. It also sanitizes authored free-text and
computes a stable `input_hash` (for bible caching) and a deterministic `seed`.

The `Checkpointer` protocol lets the orchestrator persist each node's output and
skip completed nodes on resume; an in-memory implementation is provided here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.schemas.input import GenerationContext, SimulationInput

# --------------------------------------------------------------------------- #
# canonical spec
# --------------------------------------------------------------------------- #


@dataclass
class RoundPlan:
    index: int
    dimensions: list[str]  # [] means: derive focuses at generation time
    decision_count: int = 0  # authoritative count when dimensions is []


@dataclass
class ParticipantSpec:
    context: GenerationContext
    individual_rounds: list[RoundPlan]

    @property
    def participant_id(self) -> str:
        return self.context.participant_id


@dataclass
class TeamMemberSpec:
    context: GenerationContext

    @property
    def participant_id(self) -> str:
        return self.context.participant_id


@dataclass
class TeamSpec:
    team_id: str
    team_name: str
    round_index: int
    dimensions: list[str]  # [] means: derive focuses at generation time
    members: list[TeamMemberSpec]
    decision_count: int = 0  # authoritative count when dimensions is []
    reconciliation: str = "consensus"
    reveal_mode: str = "anonymized"

    @property
    def participant_ids(self) -> list[str]:
        return [m.participant_id for m in self.members]


@dataclass
class CanonicalSpec:
    simulation_name: str
    simulation_type: str
    company_name: str
    business_context: str
    subject_matter: str
    locale: str
    seed: int
    input_hash: str
    tenant_id: str
    participants: list[ParticipantSpec]
    teams: list[TeamSpec]
    sanitize_flags: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# checkpointer
# --------------------------------------------------------------------------- #
class Checkpointer(Protocol):
    def save(self, node_id: str, value: Any) -> None: ...
    def load(self, node_id: str) -> Any | None: ...
    def has(self, node_id: str) -> bool: ...


class InMemoryCheckpointer:
    """Default checkpointer. A DB-backed one can be swapped in via the same protocol."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def save(self, node_id: str, value: Any) -> None:
        self._store[node_id] = value

    def load(self, node_id: str) -> Any | None:
        return self._store.get(node_id)

    def has(self, node_id: str) -> bool:
        return node_id in self._store


# --------------------------------------------------------------------------- #
# normalizer
# --------------------------------------------------------------------------- #
class IntakeNormalizer:
    """Deterministic intake -> CanonicalSpec transform."""

    def normalize(self, si: SimulationInput) -> CanonicalSpec:
        # Lazy import keeps the module importable without the safety package loaded
        # in pure-schema contexts; here it is always available.
        from app.safety.injection import sanitize_input

        clean_context, flags_a = sanitize_input(si.business_context)
        clean_subject, flags_b = sanitize_input(si.subject_matter)
        flags = [f"business_context:{f}" for f in flags_a] + [
            f"subject_matter:{f}" for f in flags_b
        ]

        input_hash = hashlib.sha256(si.model_dump_json().encode("utf-8")).hexdigest()
        # DECISION: when no seed is authored, derive a stable one from the input hash
        # so runs remain reproducible without forcing the author to pick a number.
        seed = si.seed if si.seed is not None else (int(input_hash[:8], 16) & 0x7FFFFFFF)

        participant_ids = [f"p{i + 1}" for i in range(si.participant_count)]
        roles = si.role_overview
        # DECISION: role_overview is a pool assigned round-robin. A role that carries
        # its own kpi_tradeoffs gives the participant exactly those dilemmas; roles
        # without their own fall back to the shared kpi_critical_tradeoff list.
        contexts: dict[str, GenerationContext] = {}
        for i, pid in enumerate(participant_ids):
            role = roles[i % len(roles)]
            contexts[pid] = GenerationContext(
                participant_id=pid,
                role_title=role.role_title,
                function=role.function,
                entity=role.entity,
                reporting_line=role.reporting_line,
                scope=role.scope,
                seniority_band=role.seniority_band,
                kpi_tradeoffs=(
                    list(role.kpi_tradeoffs)
                    if role.kpi_tradeoffs
                    else list(si.kpi_critical_tradeoff)
                ),
                locale=si.locale,
                role_context=role.context,
            )

        individual_rounds = [r for r in si.rounds if r.round_type == "individual"]
        group_rounds = [r for r in si.rounds if r.round_type == "group"]

        participants = [
            ParticipantSpec(
                context=contexts[pid],
                individual_rounds=[
                    RoundPlan(
                        index=r.index,
                        dimensions=list(r.dimensions or []),
                        decision_count=r.decision_count,
                    )
                    for r in individual_rounds
                ],
            )
            for pid in participant_ids
        ]

        teams: list[TeamSpec] = []
        for r in group_rounds:
            tc = r.team_config
            assert tc is not None  # guaranteed by RoundSpec validator
            size = tc.size
            for ti, team_name in enumerate(tc.unique_group_names):
                slice_ids = participant_ids[ti * size : (ti + 1) * size]
                if not slice_ids:
                    continue  # not enough participants to fill this team; skip
                teams.append(
                    TeamSpec(
                        team_id=f"r{r.index}_team{ti + 1}",
                        team_name=team_name,
                        round_index=r.index,
                        dimensions=list(r.dimensions or []),
                        decision_count=r.decision_count,
                        members=[TeamMemberSpec(context=contexts[pid]) for pid in slice_ids],
                        reconciliation=tc.reconciliation,
                        reveal_mode=tc.reveal_mode,
                    )
                )

        return CanonicalSpec(
            simulation_name=si.simulation_name,
            simulation_type=si.simulation_type,
            company_name=si.company_name,
            business_context=clean_context,
            subject_matter=clean_subject,
            locale=si.locale,
            seed=seed,
            input_hash=input_hash,
            tenant_id=si.tenant_id,
            participants=participants,
            teams=teams,
            sanitize_flags=flags,
        )
