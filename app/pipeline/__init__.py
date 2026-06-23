"""Generation pipeline: intake -> foundation -> fan-out -> reduce."""

from app.pipeline.assemble import (
    assemble,
    bind_scoring,
    has_review_flags,
    shuffle_positions,
)
from app.pipeline.decisions import DecisionBuild, build_decisions, decision_forge
from app.pipeline.normalize import (
    CanonicalSpec,
    Checkpointer,
    InMemoryCheckpointer,
    IntakeNormalizer,
    ParticipantSpec,
    TeamSpec,
)
from app.pipeline.orchestrator import (
    GenerationAudit,
    generate_simulation,
    generate_with_audit,
)
from app.pipeline.reduce import (
    SafetyGateError,
    editorial_gate,
    editorial_violations,
    option_word_parity_ok,
    safety_gate,
)

__all__ = [
    "IntakeNormalizer",
    "CanonicalSpec",
    "Checkpointer",
    "InMemoryCheckpointer",
    "ParticipantSpec",
    "TeamSpec",
    "generate_simulation",
    "generate_with_audit",
    "GenerationAudit",
    "build_decisions",
    "DecisionBuild",
    "decision_forge",
    "assemble",
    "shuffle_positions",
    "bind_scoring",
    "has_review_flags",
    "editorial_gate",
    "editorial_violations",
    "option_word_parity_ok",
    "safety_gate",
    "SafetyGateError",
]
