"""Intake schemas: the authored `SimulationInput` and the de-identified
`GenerationContext` that is the only thing ever sent to a model.

Validators enforce the Section 19 input rules:
- when dimensions are provided (legacy), their length must equal decision_count
- group rounds require team_config; individual rounds must not carry one
- at most MAX_TEAMS teams (Section 5.1 hard limit)
- participant_count in 1..50 and team size in 2..4 (field-level)
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator, BaseModel, Field, model_validator


# Hard ceiling mirrored from Section 5.1 / config (kept local so schema
# validation never depends on runtime settings being importable).
MAX_TEAMS = 5


_NA_LIKE = {"na", "n/a", "n.a.", "n.a", "-", "--", "none", "null", "tbd"}


def _na_to_empty(v):
    """Treat 'NA'-style placeholders as absent. Authors mark unknown cells NA in
    spreadsheets; a literal 'NA' reaching a prompt reads as content ('reports to
    NA'), so it is normalized to empty at the boundary."""
    if isinstance(v, str) and v.strip().lower() in _NA_LIKE:
        return ""
    return v


class KpiTradeoff(BaseModel):
    metric: str
    # target and competing_pressure are OPTIONAL: client data often lacks them.
    # The ROLE prompt has explicit tiered handling for their absence.
    target: str = ""
    current: str | None = None
    competing_pressure: str = ""

    @field_validator("metric", "target", "current", "competing_pressure", mode="before")
    @classmethod
    def _kpi_na(cls, v):
        return _na_to_empty(v)


class RoleOverview(BaseModel):
    role_title: str
    function: str
    entity: str = ""
    reporting_line: str = ""
    scope: str = ""

    @field_validator(
        "role_title", "function", "entity", "reporting_line", "scope", "context", mode="before"
    )
    @classmethod
    def _role_na(cls, v):
        return _na_to_empty(v)
    seniority_band: Literal["mid", "senior", "exec", "c_suite"] = "senior"
    gender: Literal["male", "female", "non_binary", "unspecified"] = "unspecified"
    # KPI trade-offs owned by THIS role. When present, the participant playing this
    # role gets exactly these dilemmas (instead of the shared flat list below).
    kpi_tradeoffs: list[KpiTradeoff] = Field(default_factory=list)
    # Optional free-text brief for this role, typically pasted or uploaded from a
    # .md/.txt file. Capped at ~1 MB of text; fed to role generation as context.
    context: str = Field(default="", max_length=1_000_000)


class RoleFieldsExtraction(BaseModel):
    """Structured fields extracted from an uploaded role brief, to pre-fill the form.

    Free-text fields are "" when the brief doesn't state them. seniority_band and
    gender fall back to their role defaults when the brief gives no signal.
    """

    role_title: str = ""
    function: str = ""
    entity: str = ""
    reporting_line: str = ""
    scope: str = ""
    seniority_band: Literal["mid", "senior", "exec", "c_suite"] = "senior"
    gender: Literal["male", "female", "non_binary", "unspecified"] = "unspecified"


class TeamConfig(BaseModel):
    size: int = Field(ge=2, le=4)
    unique_group_names: list[str] = Field(default_factory=list)
    # (team names land in a VARCHAR(255) column; cap well below it)
    reconciliation: Literal["consensus", "majority", "facilitator"] = "consensus"
    reveal_mode: Literal["anonymized", "named"] = "anonymized"

    @model_validator(mode="after")
    def _team_count_within_limit(self) -> "TeamConfig":
        if not self.unique_group_names:
            raise ValueError("team_config.unique_group_names must not be empty")
        if any(len(n) > 100 for n in self.unique_group_names):
            raise ValueError("team names must be 100 characters or fewer")
        if len(self.unique_group_names) > MAX_TEAMS:
            raise ValueError(f"at most {MAX_TEAMS} teams are allowed")
        if len(set(self.unique_group_names)) != len(self.unique_group_names):
            raise ValueError("team names must be unique")
        return self


class RoundSpec(BaseModel):
    index: int = Field(ge=1)
    round_type: Literal["individual", "group"]
    decision_count: int = Field(default=3, ge=1, le=6)
    # LEGACY/optional. When omitted (the normal path now), each decision's focus is
    # DERIVED from the simulation's teaching frame at generation time. When provided
    # (old payloads), the given tags are used as-is.
    dimensions: list[str] | None = None
    team_config: TeamConfig | None = None  # required iff round_type == "group"

    @model_validator(mode="after")
    def _validate_round(self) -> "RoundSpec":
        if self.dimensions is not None and len(self.dimensions) != self.decision_count:
            raise ValueError("dimensions length must equal decision_count")
        if self.round_type == "group" and self.team_config is None:
            raise ValueError("group rounds require a team_config")
        if self.round_type == "individual" and self.team_config is not None:
            # DECISION: individual rounds carry no team_config; reject rather than
            # silently ignore so authored input stays unambiguous.
            raise ValueError("individual rounds must not include a team_config")
        return self


class SimulationInput(BaseModel):
    simulation_name: str = Field(max_length=255)
    simulation_type: str = "immersive-sim"
    company_name: str
    business_context: str
    subject_matter: str
    participant_count: int = Field(ge=1, le=50)
    # 1 = allocation + fixed postures (default); 2 = allocation + dynamic type-set
    engine_version: int = Field(default=2, ge=1, le=2)
    rounds: list[RoundSpec]
    role_overview: list[RoleOverview]
    # Legacy/shared pool: used only for roles that do not carry their own
    # kpi_tradeoffs. Optional when every role has its own.
    kpi_critical_tradeoff: list[KpiTradeoff] = Field(default_factory=list)
    locale: str = "en-IN"
    seed: int | None = None
    tenant_id: str

    @model_validator(mode="after")
    def _validate_input(self) -> "SimulationInput":
        if not self.rounds:
            raise ValueError("at least one round is required")
        # DECISION: role_overview / kpi_critical_tradeoff are treated as pools the
        # IntakeNormalizer (Part 2) assigns to participants (cycling if shorter).
        # We only require them to be non-empty here; we do not force a length match
        # to participant_count, keeping simple single-role authoring valid.
        if not self.role_overview:
            raise ValueError("role_overview must not be empty")
        # Every role needs a dilemma set: either its own kpi_tradeoffs or the shared
        # kpi_critical_tradeoff pool as a fallback.
        if not self.kpi_critical_tradeoff:
            missing = [r.role_title for r in self.role_overview if not r.kpi_tradeoffs]
            if missing:
                raise ValueError(
                    "kpi_critical_tradeoff is empty and these roles have no "
                    f"kpi_tradeoffs of their own: {', '.join(missing)}"
                )
        return self


class GenerationContext(BaseModel):
    """De-identified per-participant context. The ONLY participant data a prompt
    ever sees. No names, emails, employee ids, or other PII."""

    participant_id: str
    role_title: str
    function: str
    entity: str
    reporting_line: str
    scope: str
    seniority_band: str
    kpi_tradeoffs: list[KpiTradeoff]
    locale: str = "en-IN"
    # Optional role brief carried over from RoleOverview.context (e.g. an uploaded
    # .md/.txt). Not PII: intended as role responsibilities/mandate context.
    role_context: str = ""