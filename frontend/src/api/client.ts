import type {
  AuthResponse,
  Commitment,
  CreateSimulationResponse,
  DebriefResponse,
  FlaggedDecision,
  GroupAnalytics,
  LetterUnits,
  LogsResponse,
  MappingResponse,
  PostureUnits,
  Reflection,
  RenderedSession,
  RoleFieldsExtraction,
  SimContent,
  SimContentResponse,
  SimulationImage,
  SimulationDetailMeta,
  SimulationInput,
  SimulationListItem,
  StatusResponse,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api";

/** A failed API call, carrying the HTTP status and the server's message. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(
  path: string,
  init: RequestInit & { token?: string; idempotencyKey?: string } = {},
): Promise<T> {
  const { token, idempotencyKey, headers, ...rest } = init;
  const merged: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? authHeader(token) : {}),
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    ...((headers as Record<string, string>) ?? {}),
  };

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...rest, headers: merged });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the API running?");
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  const body = text ? safeJson(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(body) ?? `Request failed (${res.status}).`);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function extractDetail(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // pydantic validation errors -> a readable summary
      return detail
        .map((e) => {
          const loc = Array.isArray((e as { loc?: unknown[] }).loc)
            ? (e as { loc: unknown[] }).loc.join(".")
            : "";
          return `${loc}: ${(e as { msg?: string }).msg ?? "invalid"}`;
        })
        .join("; ");
    }
  }
  return null;
}

export const api = {
  // ---- auth ----
  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, workspace_name?: string) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, workspace_name }),
    }),

  me: (token: string) =>
    request<{ user_id: string; email: string; tenant_id: string }>("/auth/me", { token }),

  // ---- dashboard / detail ----
  listSimulations: (token: string) =>
    request<{ simulations: SimulationListItem[] }>("/simulations", { token }),

  getSimulation: (simulationId: string, token: string) =>
    request<SimulationDetailMeta>(`/simulations/${simulationId}`, { token }),

  getContent: (simulationId: string, token: string) =>
    request<SimContentResponse>(`/simulations/${simulationId}/content`, { token }),

  updateContent: (simulationId: string, token: string, sim_data: SimContent) =>
    request<{ simulation_id: string; version: number | null; saved: boolean }>(
      `/simulations/${simulationId}/content`,
      { method: "PUT", token, body: JSON.stringify({ sim_data }) },
    ),

  listImages: (simulationId: string, token: string) =>
    request<{ images: SimulationImage[] }>(`/simulations/${simulationId}/images`, { token }),

  addImage: (simulationId: string, token: string, name: string, data: string) =>
    request<SimulationImage>(`/simulations/${simulationId}/images`, {
      method: "POST",
      token,
      body: JSON.stringify({ name, data }),
    }),

  deleteImage: (simulationId: string, token: string, name: string) =>
    request<{ deleted: boolean; name: string }>(
      `/simulations/${simulationId}/images/${encodeURIComponent(name)}`,
      { method: "DELETE", token },
    ),

  getLogs: (simulationId: string, token: string) =>
    request<LogsResponse>(`/simulations/${simulationId}/logs`, { token }),

  getMapping: (simulationId: string, token: string) =>
    request<MappingResponse>(`/simulations/${simulationId}/mapping`, { token }),

  // ---- authoring ----
  createSimulation: (input: SimulationInput, token: string, idempotencyKey: string) =>
    request<CreateSimulationResponse>("/simulations", {
      method: "POST",
      body: JSON.stringify(input),
      token,
      idempotencyKey,
    }),

  parseRole: (token: string, text: string) =>
    request<RoleFieldsExtraction>("/simulations/parse-role", {
      method: "POST",
      token,
      body: JSON.stringify({ text }),
    }),

  getStatus: (simulationId: string, token: string) =>
    request<StatusResponse>(`/simulations/${simulationId}/status`, { token }),

  runJobs: (simulationId: string, token: string) =>
    request<StatusResponse & { jobs_handled: number }>(`/simulations/${simulationId}/run`, {
      method: "POST",
      token,
    }),

  listFlagged: (simulationId: string, token: string) =>
    request<{ flagged: FlaggedDecision[]; count: number }>(
      `/simulations/${simulationId}/review`,
      { token },
    ),

  submitReview: (
    simulationId: string,
    token: string,
    body: { reviewer: string; action: "approve" | "reject"; notes?: string },
  ) =>
    request<{ simulation_id: string; status: string; action: string }>(
      `/simulations/${simulationId}/review`,
      { method: "POST", body: JSON.stringify(body), token },
    ),

  // ---- runtime ----
  createSession: (
    token: string,
    body: { simulation_id: string; participant_ref: string; display_seed?: number },
  ) =>
    request<{ session_id: string; simulation_version_id: string }>("/sessions", {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  getSession: (sessionId: string, token: string) =>
    request<RenderedSession>(`/sessions/${sessionId}`, { token }),

  submitAllocations: (
    sessionId: string,
    token: string,
    allocations: { decision_number: number; units: LetterUnits }[],
  ) =>
    request<{ submitted: number }>(`/sessions/${sessionId}/allocations`, {
      method: "POST",
      body: JSON.stringify({ allocations }),
      token,
    }),

  submitReflection: (
    sessionId: string,
    token: string,
    body: { decision_number: number; reflection: Reflection },
  ) =>
    request<{ status: string }>(`/sessions/${sessionId}/reflections`, {
      method: "POST",
      body: JSON.stringify(body),
      token,
    }),

  submitCommitment: (sessionId: string, token: string, commitment: Commitment) =>
    request<{ status: string }>(`/sessions/${sessionId}/commitments`, {
      method: "POST",
      body: JSON.stringify({ commitment }),
      token,
    }),

  getDebrief: (sessionId: string, token: string) =>
    request<DebriefResponse>(`/sessions/${sessionId}/debrief`, { token }),

  // ---- groups ----
  reconcileTeam: (
    teamId: string,
    token: string,
    allocations: { decision_number: number; units: PostureUnits }[],
  ) =>
    request<{ analytics: GroupAnalytics }>(`/teams/${teamId}/reconcile`, {
      method: "POST",
      body: JSON.stringify({ allocations }),
      token,
    }),

  getTeamAnalytics: (teamId: string, token: string) =>
    request<{ analytics: GroupAnalytics; team_allocations: unknown[] }>(
      `/teams/${teamId}/analytics`,
      { token },
    ),
};
