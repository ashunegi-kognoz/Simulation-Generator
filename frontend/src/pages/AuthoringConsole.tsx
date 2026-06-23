import { useState } from "react";
import { ApiError, api } from "../api/client";
import type {
  Dimension,
  FlaggedDecision,
  KpiTradeoff,
  RoleOverview,
  RoundSpec,
  SimulationInput,
  StatusResponse,
} from "../api/types";
import { Banner, Panel, Spinner, StatusBadge } from "../components/ui";

const DIMENSIONS: Dimension[] = ["MOVE", "HOLD", "FRAME"];
const BANDS: RoleOverview["seniority_band"][] = ["mid", "senior", "exec", "c_suite"];
const TERMINAL = new Set(["ready", "needs_review", "failed"]);

function defaultInput(): Omit<SimulationInput, "tenant_id"> {
  return {
    simulation_name: "Q3 Allocation Room",
    simulation_type: "immersive-sim",
    company_name: "Apex Horizon Group",
    business_context:
      "Apex Horizon Group's logistics arm is under margin pressure while a service-level promise to top accounts is slipping.",
    subject_matter: "supply chain resilience",
    participant_count: 3,
    locale: "en-IN",
    rounds: [
      { index: 1, round_type: "individual", decision_count: 2, dimensions: ["MOVE", "HOLD"] },
    ],
    role_overview: [
      {
        role_title: "Regional Director",
        function: "Operations",
        entity: "AHG Logistics",
        reporting_line: "COO",
        scope: "South region",
        seniority_band: "exec",
      },
    ],
    kpi_critical_tradeoff: [
      { metric: "OTIF", target: "95%", competing_pressure: "freight cost" },
    ],
  };
}

function resizeDimensions(dims: Dimension[], count: number): Dimension[] {
  const out = dims.slice(0, count);
  while (out.length < count) out.push("MOVE");
  return out;
}

export function AuthoringConsole({
  token,
  tenantId,
  onOpenDetail,
  onBack,
}: {
  token: string;
  tenantId: string;
  onOpenDetail: (simulationId: string) => void;
  onBack: () => void;
}) {
  const [form, setForm] = useState(defaultInput);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [simulationId, setSimulationId] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [flagged, setFlagged] = useState<FlaggedDecision[] | null>(null);

  function patch(p: Partial<typeof form>) {
    setForm((f) => ({ ...f, ...p }));
  }
  function patchRound(i: number, p: Partial<RoundSpec>) {
    setForm((f) => ({
      ...f,
      rounds: f.rounds.map((r, idx) => (idx === i ? { ...r, ...p } : r)),
    }));
  }
  function patchRole(i: number, p: Partial<RoleOverview>) {
    setForm((f) => ({
      ...f,
      role_overview: f.role_overview.map((r, idx) => (idx === i ? { ...r, ...p } : r)),
    }));
  }
  function patchKpi(i: number, p: Partial<KpiTradeoff>) {
    setForm((f) => ({
      ...f,
      kpi_critical_tradeoff: f.kpi_critical_tradeoff.map((k, idx) =>
        idx === i ? { ...k, ...p } : k,
      ),
    }));
  }

  async function generate() {
    if (!token || !tenantId) {
      setError("Your session is missing tenant information. Please sign in again.");
      return;
    }
    setBusy(true);
    setError(null);
    setFlagged(null);
    setStatus(null);
    try {
      const input: SimulationInput = { ...form, tenant_id: tenantId };
      const idem = `author-${crypto.randomUUID()}`;
      const created = await api.createSimulation(input, token, idem);
      setSimulationId(created.simulation_id);

      let s: StatusResponse = await api.runJobs(created.simulation_id, token);
      let tries = 0;
      while (!TERMINAL.has(s.status) && tries < 30) {
        await sleep(1000);
        s = await api.getStatus(created.simulation_id, token);
        tries += 1;
      }
      setStatus(s);
      if (s.status === "needs_review") {
        const f = await api.listFlagged(created.simulation_id, token);
        setFlagged(f.flagged);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function review(action: "approve" | "reject") {
    if (!simulationId) return;
    setBusy(true);
    setError(null);
    try {
      await api.submitReview(simulationId, token, { reviewer: "facilitator", action });
      const s = await api.getStatus(simulationId, token);
      setStatus(s);
      if (action === "approve" && s.status === "ready") {
        setFlagged(null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Review failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <button className="text-sm font-medium text-muted hover:text-ink" onClick={onBack}>
        ← All simulations
      </button>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel eyebrow="Create" title="New simulation">
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Text label="Simulation name" value={form.simulation_name} onChange={(v) => patch({ simulation_name: v })} />
            <Text label="Company" value={form.company_name} onChange={(v) => patch({ company_name: v })} />
            <Text label="Subject matter" value={form.subject_matter} onChange={(v) => patch({ subject_matter: v })} />
            <Number
              label="Participants (1–20)"
              value={form.participant_count}
              min={1}
              max={20}
              onChange={(v) => patch({ participant_count: v })}
            />
          </div>
          <div>
            <label className="label">Business context</label>
            <textarea
              className="input min-h-[84px] resize-y"
              value={form.business_context}
              onChange={(e) => patch({ business_context: e.target.value })}
            />
          </div>

          {/* rounds */}
          <Section
            title="Rounds"
            onAdd={() =>
              patch({
                rounds: [
                  ...form.rounds,
                  {
                    index: form.rounds.length + 1,
                    round_type: "individual",
                    decision_count: 2,
                    dimensions: ["MOVE", "HOLD"],
                  },
                ],
              })
            }
          >
            {form.rounds.map((r, i) => (
              <div key={i} className="rounded-xl border border-line p-3">
                <div className="grid gap-3 sm:grid-cols-3">
                  <Select
                    label="Type"
                    value={r.round_type}
                    options={["individual", "group"]}
                    onChange={(v) =>
                      patchRound(i, {
                        round_type: v as RoundSpec["round_type"],
                        team_config:
                          v === "group"
                            ? { size: 2, unique_group_names: ["Alpha", "Beta"], reconciliation: "consensus", reveal_mode: "anonymized" }
                            : null,
                      })
                    }
                  />
                  <Number
                    label="Decisions (1–6)"
                    value={r.decision_count}
                    min={1}
                    max={6}
                    onChange={(v) =>
                      patchRound(i, {
                        decision_count: v,
                        dimensions: resizeDimensions(r.dimensions, v),
                      })
                    }
                  />
                  {form.rounds.length > 1 && (
                    <button
                      className="btn-ghost mt-6 h-9 text-coral"
                      onClick={() => patch({ rounds: form.rounds.filter((_, idx) => idx !== i) })}
                    >
                      Remove round
                    </button>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {r.dimensions.map((d, di) => (
                    <select
                      key={di}
                      className="input w-auto"
                      value={d}
                      onChange={(e) => {
                        const next = r.dimensions.slice();
                        next[di] = e.target.value as Dimension;
                        patchRound(i, { dimensions: next });
                      }}
                    >
                      {DIMENSIONS.map((dim) => (
                        <option key={dim} value={dim}>{dim}</option>
                      ))}
                    </select>
                  ))}
                </div>
                {r.round_type === "group" && r.team_config && (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <Number
                      label="Team size (2–4)"
                      value={r.team_config.size}
                      min={2}
                      max={4}
                      onChange={(v) =>
                        patchRound(i, { team_config: { ...r.team_config!, size: v } })
                      }
                    />
                    <Text
                      label="Team names (comma-separated)"
                      value={r.team_config.unique_group_names.join(", ")}
                      onChange={(v) =>
                        patchRound(i, {
                          team_config: {
                            ...r.team_config!,
                            unique_group_names: v.split(",").map((s) => s.trim()).filter(Boolean),
                          },
                        })
                      }
                    />
                  </div>
                )}
              </div>
            ))}
          </Section>

          {/* roles */}
          <Section
            title="Roles (assigned round-robin)"
            onAdd={() =>
              patch({
                role_overview: [
                  ...form.role_overview,
                  { role_title: "", function: "", entity: form.company_name, reporting_line: "", scope: "", seniority_band: "senior" },
                ],
              })
            }
          >
            {form.role_overview.map((role, i) => (
              <div key={i} className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-2">
                <Text label="Role title" value={role.role_title} onChange={(v) => patchRole(i, { role_title: v })} />
                <Text label="Function" value={role.function} onChange={(v) => patchRole(i, { function: v })} />
                <Text label="Entity" value={role.entity} onChange={(v) => patchRole(i, { entity: v })} />
                <Text label="Reporting line" value={role.reporting_line} onChange={(v) => patchRole(i, { reporting_line: v })} />
                <Text label="Scope" value={role.scope} onChange={(v) => patchRole(i, { scope: v })} />
                <Select
                  label="Seniority"
                  value={role.seniority_band}
                  options={BANDS}
                  onChange={(v) => patchRole(i, { seniority_band: v as RoleOverview["seniority_band"] })}
                />
                {form.role_overview.length > 1 && (
                  <button
                    type="button"
                    className="justify-self-start text-xs font-medium text-coral hover:underline sm:col-span-2"
                    onClick={() =>
                      patch({ role_overview: form.role_overview.filter((_, idx) => idx !== i) })
                    }
                  >
                    Remove role
                  </button>
                )}
              </div>
            ))}
          </Section>

          {/* kpis */}
          <Section
            title="Critical KPI tradeoffs"
            onAdd={() =>
              patch({
                kpi_critical_tradeoff: [
                  ...form.kpi_critical_tradeoff,
                  { metric: "", target: "", competing_pressure: "" },
                ],
              })
            }
          >
            {form.kpi_critical_tradeoff.map((k, i) => (
              <div key={i} className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-3">
                <Text label="Metric" value={k.metric} onChange={(v) => patchKpi(i, { metric: v })} />
                <Text label="Target" value={k.target} onChange={(v) => patchKpi(i, { target: v })} />
                <Text label="Competing pressure" value={k.competing_pressure} onChange={(v) => patchKpi(i, { competing_pressure: v })} />
                {form.kpi_critical_tradeoff.length > 1 && (
                  <button
                    type="button"
                    className="justify-self-start text-xs font-medium text-coral hover:underline sm:col-span-3"
                    onClick={() =>
                      patch({
                        kpi_critical_tradeoff: form.kpi_critical_tradeoff.filter((_, idx) => idx !== i),
                      })
                    }
                  >
                    Remove tradeoff
                  </button>
                )}
              </div>
            ))}
          </Section>

          {error && <Banner tone="error" title="Couldn't generate">{error}</Banner>}

          <div className="flex items-center gap-3">
            <button className="btn-primary" onClick={generate} disabled={busy}>
              {busy ? "Working…" : "Create and generate"}
            </button>
            {busy && <Spinner label="Running the generation pipeline" />}
          </div>
        </div>
      </Panel>

      {/* status / review column */}
      <div className="space-y-6">
        <Panel eyebrow="Pipeline" title="Status">
          {!status && !busy && (
            <Banner tone="empty">No run yet. Compose a simulation and generate it.</Banner>
          )}
          {status && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted">Simulation</span>
                <StatusBadge status={status.status} />
              </div>
              <div className="num rounded-xl border border-line bg-canvas px-3 py-2 text-xs text-muted">
                {simulationId}
              </div>
              <div className="grid grid-cols-2 gap-2.5 text-sm">
                <KV k="Version" v={status.version ?? "—"} />
                <KV k="Flagged" v={status.flagged_count} />
              </div>
              {status.status === "failed" && status.job_error && (
                <Banner tone="error" title="Generation failed">{status.job_error}</Banner>
              )}
              {status.status === "ready" && (
                <Banner tone="info" title="Ready">
                  Open the Run workspace to start a participant session.
                </Banner>
              )}
            </div>
          )}
          {simulationId && (
            <button
              className="btn-primary mt-4 w-full"
              onClick={() => onOpenDetail(simulationId)}
            >
              Open simulation →
            </button>
          )}
        </Panel>

        {flagged && (
          <Panel eyebrow="Review" title={`Flagged decisions (${flagged.length})`}>
            <div className="space-y-3">
              {flagged.length === 0 && <Banner tone="empty">Nothing flagged.</Banner>}
              {flagged.map((f, i) => (
                <div key={i} className="rounded-xl border border-line p-3">
                  <div className="flex items-center justify-between text-xs text-muted">
                    <span className="num">{f.owner_id} · D{f.decision_number}</span>
                    <span className="rounded-full bg-canvas px-2 py-0.5 font-medium text-ink">{f.dimension}</span>
                  </div>
                  <div className="mt-1 text-sm font-medium text-ink">{f.decision.title}</div>
                  <p className="mt-1 text-sm text-muted">{f.decision.question}</p>
                </div>
              ))}
              <div className="flex gap-3">
                <button className="btn-primary" onClick={() => review("approve")} disabled={busy}>
                  Approve and publish
                </button>
                <button className="btn-ghost text-coral" onClick={() => review("reject")} disabled={busy}>
                  Reject
                </button>
              </div>
            </div>
          </Panel>
        )}
      </div>
    </div>
    </div>
  );
}

// ---- small form atoms (local to authoring) ----
function Text({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="label">{label}</label>
      <input className="input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
function Number({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        type="number"
        className="input num"
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(parseInt(e.target.value || "0", 10))}
      />
    </div>
  );
}
function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}
function Section({ title, onAdd, children }: { title: string; onAdd: () => void; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="eyebrow">{title}</h3>
        <button className="text-xs font-medium text-petrol hover:text-petrol-hover" onClick={onAdd}>
          + Add
        </button>
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}
function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-canvas px-3 py-2">
      <div className="eyebrow">{k}</div>
      <div className="num mt-0.5 text-ink">{v}</div>
    </div>
  );
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
