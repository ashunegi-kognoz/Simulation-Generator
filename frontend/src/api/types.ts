// TypeScript mirrors of the Part 1-3 server schemas. Rendered options are
// letters-only by design — there is intentionally no `posture` field here.

export type Dimension = "MOVE" | "HOLD" | "FRAME";
export type Posture = "Protect" | "Enable" | "Hybrid" | "Defer";
export type Letter = "A" | "B" | "C" | "D";
export const LETTERS: Letter[] = ["A", "B", "C", "D"];
export const POSTURES: Posture[] = ["Protect", "Enable", "Hybrid", "Defer"];

export type SimulationStatus =
  | "queued"
  | "generating"
  | "needs_review"
  | "ready"
  | "failed";

// ---- authoring input ----
export interface RoleOverview {
  role_title: string;
  function: string;
  entity: string;
  reporting_line: string;
  scope: string;
  seniority_band: "mid" | "senior" | "exec" | "c_suite";
  context?: string;
}

export interface KpiTradeoff {
  metric: string;
  target: string;
  current?: string | null;
  competing_pressure: string;
}

export interface TeamConfig {
  size: number;
  unique_group_names: string[];
  reconciliation: "consensus" | "majority" | "facilitator";
  reveal_mode: "anonymized" | "named";
}

export interface RoundSpec {
  index: number;
  round_type: "individual" | "group";
  decision_count: number;
  dimensions: Dimension[];
  team_config?: TeamConfig | null;
}

export interface SimulationInput {
  simulation_name: string;
  simulation_type?: string;
  company_name: string;
  business_context: string;
  subject_matter: string;
  participant_count: number;
  rounds: RoundSpec[];
  role_overview: RoleOverview[];
  kpi_critical_tradeoff: KpiTradeoff[];
  locale?: string;
  seed?: number | null;
  tenant_id: string;
}

// ---- authoring responses ----
export interface CreateSimulationResponse {
  simulation_id: string;
  job_id: string;
  status: SimulationStatus;
}

export interface StatusResponse {
  simulation_id: string;
  status: SimulationStatus;
  job_status: "queued" | "running" | "completed" | "failed" | null;
  job_error: string | null;
  needs_review: boolean;
  flagged_count: number;
  version: number | null;
}

export interface FlaggedDecision {
  owner_type: string;
  owner_id: string;
  round_index: number;
  decision_number: number;
  dimension: Dimension;
  decision: RenderedDecisionRaw;
  balance_report: unknown | null;
}

// ---- runtime ----
export interface RenderedOption {
  letter: Letter;
  label: string;
  content: string;
}

export interface RenderedDecision {
  decision_number: number;
  dimension: Dimension;
  title: string;
  question: string;
  options: RenderedOption[];
}

// the authoring review endpoint returns the canonical (posture-tagged) decision
export interface RenderedDecisionRaw {
  decision_number: number;
  dimension: Dimension;
  title: string;
  question: string;
  options: { posture: Posture; label: string; content: string }[];
}

export interface RenderedSession {
  session_id: string;
  decisions: RenderedDecision[];
}

export type LetterUnits = Record<Letter, number>;
export type PostureUnits = Record<Posture, number>;

export interface Reflection {
  considered_most?: string | null;
  resisted?: string | null;
  uncertain?: string | null;
}

export interface Commitment {
  action: string;
  share_with: string;
  by_when: string;
}

// ---- scoring / debrief ----
export interface PostureFingerprint {
  overall: Record<Posture, number>;
  by_dimension: Record<Dimension, Record<Posture, number>>;
  decisiveness: number;
  consistency: number;
  dimension_sensitivity: number;
  protect_index: number;
  enable_index: number;
  hybrid_index: number;
  defer_index: number;
  reliability: "low" | "moderate" | "high";
  n_decisions: number;
}

export interface Debrief {
  pattern_summary: string;
  interpretation: string;
  tension_navigated: string;
  blind_spot: string;
  transfer_prompt: string;
  cited_decisions: number[];
}

export interface DebriefResponse {
  fingerprint: PostureFingerprint;
  debrief: Debrief;
}

export interface GroupAnalytics {
  per_decision_dispersion: Record<string, number>;
  per_decision_movement: Record<string, number>;
  anchor_participant: string | null;
  biggest_mover: string | null;
  posture_diversity: number;
}

// ---- dashboard / detail (flow restructure) ----
export interface SimulationListItem {
  id: string;
  name: string;
  status: SimulationStatus;
  created_at: string;
  participant_count: number | null;
  round_count: number;
  version: number | null;
}

export interface SimContentOption {
  posture: Posture;
  label: string;
  content: string;
}
export interface SimContentDecision {
  decision_number: number;
  dimension: Dimension;
  title: string;
  question: string;
  options: SimContentOption[];
}
export interface SimContentParticipant {
  participant_id: string;
  role_data: string;
  situation_data: string;
  decision_board: SimContentDecision[];
}
export interface SimContentMember {
  situation_data: string;
  decision_board: SimContentDecision[];
}
export interface SimContentTeam {
  team_id: string;
  team_name: string;
  scenario_data: string;
  participant_ids: string[];
  members: Record<string, SimContentMember>;
}
export interface SimContentRound {
  round_type: "individual" | "group";
  participants: Record<string, SimContentParticipant> | null;
  teams: Record<string, SimContentTeam> | null;
}
export interface SimContent {
  common_data: {
    allocation_room_data: string;
    business_landscape: string;
    business_priorities: string[];
    crisis_data: string;
    reflection_board_helping_data: string;
    posture_scheme?: PostureScheme;
  };
  rounds: Record<string, SimContentRound>;
}

export interface PostureScheme {
  inferred_category: string;
  protect_label: string;
  protect_definition: string;
  enable_label: string;
  enable_definition: string;
  hybrid_label: string;
  hybrid_definition: string;
  defer_label: string;
  defer_definition: string;
}
export interface SimContentResponse {
  simulation_id: string;
  name: string;
  status: SimulationStatus;
  version: number | null;
  sim_data: SimContent | null;
}

export interface GenerationRunLog {
  stage: string;
  model: string | null;
  prompt_version: string | null;
  seed: number | null;
  tokens: number | null;
  latency_ms: number | null;
  created_at: string;
}
export interface LogsResponse {
  job: { id: string; status: string | null; error: string | null; created_at: string } | null;
  runs: GenerationRunLog[];
}

export interface MappingParticipant {
  ref: string;
  role_title: string | null;
  function: string | null;
  entity: string | null;
  seniority_band: string | null;
}
export interface MappingTeam {
  id: string;
  name: string;
  round_index: number;
  members: string[];
}
export interface MappingResponse {
  participants: MappingParticipant[];
  teams: MappingTeam[];
}

export interface SimulationDetailMeta {
  id: string;
  name: string;
  status: SimulationStatus;
  version: number | null;
  simulation_version_id: string | null;
  created_at: string | null;
  input: SimulationInput | null;
}

// ---- auth ----
export interface AuthResponse {
  access_token: string;
  token_type: string;
  email: string;
  tenant_id: string;
}
