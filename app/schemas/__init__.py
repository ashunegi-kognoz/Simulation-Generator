"""Re-export every schema so callers can `from app.schemas import X`."""

from app.schemas.common import (
    DIMENSIONS,
    POSTURE_SET,
    POSTURES,
    SORTED_POSTURES,
    Dimension,
    Posture,
)
from app.schemas.content import (
    BalanceReport,
    CommonData,
    PostureScheme,
    ConsistencyReport,
    Decision,
    DecisionSet,
    MemberRoundData,
    NaiveScores,
    NarrativeBible,
    Option,
    ParticipantContent,
    RoleSituation,
    RoundOutput,
    ScenarioText,
    SituationText,
    Stakeholder,
    TeamContent,
)
from app.schemas.input import (
    GenerationContext,
    KpiTradeoff,
    RoleOverview,
    RoundSpec,
    SimulationInput,
    TeamConfig,
)
from app.schemas.metadata import GenerationMetadata, SimData, SimulationOutput
from app.schemas.runtime import (
    Allocation,
    Commitment,
    Reflection,
    RenderedDecision,
    RenderedOption,
)
from app.schemas.scoring import Debrief, GroupAnalytics, PostureFingerprint

__all__ = [
    # common
    "Posture",
    "Dimension",
    "POSTURES",
    "DIMENSIONS",
    "POSTURE_SET",
    "SORTED_POSTURES",
    # input
    "KpiTradeoff",
    "RoleOverview",
    "TeamConfig",
    "RoundSpec",
    "SimulationInput",
    "GenerationContext",
    # content
    "Stakeholder",
    "NarrativeBible",
    "CommonData",
    "PostureScheme",
    "Option",
    "Decision",
    "DecisionSet",
    "RoleSituation",
    "ParticipantContent",
    "MemberRoundData",
    "TeamContent",
    "RoundOutput",
    "BalanceReport",
    "NaiveScores",
    "ConsistencyReport",
    "ScenarioText",
    "SituationText",
    # metadata
    "GenerationMetadata",
    "SimData",
    "SimulationOutput",
    # runtime
    "RenderedOption",
    "RenderedDecision",
    "Allocation",
    "Reflection",
    "Commitment",
    # scoring
    "PostureFingerprint",
    "GroupAnalytics",
    "Debrief",
]
