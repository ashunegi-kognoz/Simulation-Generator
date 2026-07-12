import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import type {
  SimulationInput,
  FlaggedDecision,
  SimulationDetailMeta,
  SimulationStatus,
  StatusResponse,
} from "../../api/types";
import { Banner, Panel, Spinner, Stat, StatusBadge } from "../../components/ui";

const TERMINAL = new Set<SimulationStatus>(["ready", "needs_review", "failed"]);

export function DetailsSettings({
  meta,
  token,
  onStatusChange,
}: {
  meta: SimulationDetailMeta;
  token: string;
  onStatusChange?: (status: SimulationStatus) => void;
}) {
  const simulationId = meta.id;
  const input = meta.input;
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [flagged, setFlagged] = useState<FlaggedDecision[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SimulationInput | null>(null);
  const [reviseInfo, setReviseInfo] = useState<string | null>(null);

  const startEdit = () => {
    if (!input) return;
    setDraft(JSON.parse(JSON.stringify(input)) as SimulationInput);
    setReviseInfo(null);
    setEditing(true);
  };

  const patchDraft = (fn: (d: SimulationInput) => void) => {
    setDraft((d) => {
      if (!d) return d;
      const next = JSON.parse(JSON.stringify(d)) as SimulationInput;
      fn(next);
      return next;
    });
  };

  const submitRevise = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.revise(simulationId, token, draft);
      const scopeMsg =
        res.scope === "full"
          ? "Spec-level inputs changed — regenerating the whole simulation."
          : res.regenerating_participants.length || res.regenerating_teams.length
            ? `Regenerating only: ${[...res.regenerating_participants, ...res.regenerating_teams].join(", ")} (everything else reused).`
            : "No generated content affected by this edit.";
      setReviseInfo(scopeMsg);
      setEditing(false);
      const s2 = await api.runJobs(simulationId, token);
      setStatus(s2);
      onStatusChange?.(s2.status);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Regeneration failed");
    } finally {
      setBusy(false);
    }
  };
  const timer = useRef<number | null>(null);

  const refresh = useCallback(
    async (quiet = false) => {
      try {
        const s = await api.getStatus(simulationId, token);
        setStatus(s);
        onStatusChange?.(s.status);
        if (s.status === "needs_review") {
          const f = await api.listFlagged(simulationId, token);
          setFlagged(f.flagged);
        } else {
          setFlagged(null);
        }
      } catch (e) {
        if (!quiet) setError(e instanceof ApiError ? e.message : "Couldn't load status.");
      }
    },
    [simulationId, token, onStatusChange],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // poll while generating
  useEffect(() => {
    if (status && !TERMINAL.has(status.status)) {
      timer.current = window.setInterval(() => void refresh(true), 2000);
      return () => {
        if (timer.current) window.clearInterval(timer.current);
      };
    }
    if (timer.current) window.clearInterval(timer.current);
  }, [status, refresh]);

  async function runGeneration() {
    setBusy(true);
    setError(null);
    try {
      const s = await api.runJobs(simulationId, token);
      setStatus(s);
      onStatusChange?.(s.status);
      await refresh(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't run generation.");
    } finally {
      setBusy(false);
    }
  }

  async function review(action: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await api.submitReview(simulationId, token, { reviewer: "facilitator", action });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Review failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
      {/* settings summary */}
      <Panel eyebrow="Simulation details & settings" title="Configuration">
        {!input ? (
          <Banner tone="empty">Configuration is unavailable for this simulation.</Banner>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              <Stat label="Company" value={<span className="text-sm">{input.company_name}</span>} />
              <Stat label="Participants" value={input.participant_count} />
              <Stat label="Rounds" value={input.rounds.length} />
              <Stat label="Subject" value={<span className="text-sm">{input.subject_matter}</span>} />
              <Stat label="Locale" value={<span className="text-sm">{input.locale ?? "—"}</span>} />
              <Stat label="Roles" value={input.role_overview.length} />
            </div>

            <div>
              <div className="eyebrow mb-1">Business context</div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
                {input.business_context}
              </p>
            </div>

            <div>
              <div className="eyebrow mb-2">Rounds</div>
              <div className="space-y-2">
                {input.rounds.map((r, i) => (
                  <div
                    key={i}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line bg-canvas px-3 py-2 text-sm"
                  >
                    <span className="num font-semibold text-ink">Round {r.index}</span>
                    <span className="rounded-full bg-panel px-2 py-0.5 text-xs font-medium text-ink">
                      {r.round_type}
                    </span>
                    <span className="text-muted">{r.decision_count} decisions</span>
                    {r.dimensions && r.dimensions.length > 0 && (
                      <span className="num text-xs text-faint">{r.dimensions.join(" · ")}</span>
                    )}
                    {r.round_type === "group" && r.team_config && (
                      <span className="text-xs text-muted">
                        teams of {r.team_config.size} · {r.team_config.unique_group_names.join(", ")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <div className="eyebrow mb-2">Roles</div>
                <ul className="space-y-1.5 text-sm">
                  {input.role_overview.map((role, i) => (
                    <li key={i} className="rounded-lg border border-line px-3 py-1.5">
                      <span className="font-medium text-ink">{role.role_title}</span>
                      <span className="text-muted"> · {role.function}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="eyebrow mb-2">KPI tradeoffs</div>
                <ul className="space-y-1.5 text-sm">
                  {input.kpi_critical_tradeoff.map((k, i) => (
                    <li key={i} className="rounded-lg border border-line px-3 py-1.5">
                      <span className="font-medium text-ink">{k.metric}</span>
                      <span className="text-muted"> → {k.target}</span>
                      <span className="text-faint"> vs {k.competing_pressure}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
            <p className="text-xs text-faint">
              Configuration is read-only after creation. To change it, create a new simulation.
            </p>
          </div>
        )}
      </Panel>

      {/* status + review */}
      <div className="space-y-6">
        <Panel eyebrow="Pipeline" title="Run status">
          {!status ? (
            <Spinner label="Loading status…" />
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted">Simulation</span>
                <StatusBadge status={status.status} />
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                <Stat label="Version" value={status.version ?? "—"} />
                <Stat label="Flagged" value={status.flagged_count} />
              </div>
              {!TERMINAL.has(status.status) && <Spinner label="Generating…" />}
              {status.status === "failed" && status.job_error && (
                <Banner tone="error" title="Generation failed">{status.job_error}</Banner>
              )}
              {status.status === "queued" && (
                <button className="btn-primary w-full" onClick={runGeneration} disabled={busy}>
                  {busy ? "Working…" : "Run generation"}
                </button>
              )}
              {status.status === "ready" && (
                <Banner tone="info" title="Ready">
                  This simulation is published. Open the User &amp; Group mapping to run sessions.
                </Banner>
              )}
            </div>
          )}
          {error && (
            <div className="mt-3">
              <Banner tone="error">{error}</Banner>
            </div>
          )}
        </Panel>

        {status?.status === "needs_review" && (
          <Panel eyebrow="Review" title={`Flagged decisions (${flagged?.length ?? 0})`}>
            <div className="space-y-3">
              {flagged && flagged.length === 0 && (
                <Banner tone="warn" title="Needs sign-off">
                  Review was triggered by a consistency or editorial check rather than a specific
                  decision. You can approve and publish.
                </Banner>
              )}
              {flagged?.map((f, i) => (
                <div key={i} className="rounded-xl border border-line p-3">
                  <div className="flex items-center justify-between text-xs text-muted">
                    <span className="num">
                      {f.owner_id} · D{f.decision_number}
                    </span>
                    <span className="rounded-full bg-canvas px-2 py-0.5 font-medium text-ink">
                      {f.dimension}
                    </span>
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

      <Panel eyebrow="Revisions" title="Edit inputs & regenerate">
        {reviseInfo && <Banner tone="info">{reviseInfo}</Banner>}
        {!editing ? (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-muted">
              Change the inputs and regenerate as a new revision. Role-only edits regenerate just
              the affected participants; changes to context, subject, rounds, or engine regenerate
              the whole simulation. Prior revisions stay intact.
            </p>
            <button className="btn-primary shrink-0" onClick={startEdit} disabled={!input || busy}>
              Edit inputs
            </button>
          </div>
        ) : draft ? (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="eyebrow mb-1 block">Simulation name</span>
                <input className="input w-full" value={draft.simulation_name}
                  onChange={(e) => patchDraft((d) => { d.simulation_name = e.target.value; })} />
              </label>
              <label className="block text-sm">
                <span className="eyebrow mb-1 block">Company</span>
                <input className="input w-full" value={draft.company_name}
                  onChange={(e) => patchDraft((d) => { d.company_name = e.target.value; })} />
              </label>
            </div>
            <label className="block text-sm">
              <span className="eyebrow mb-1 block">Subject matter</span>
              <input className="input w-full" value={draft.subject_matter}
                onChange={(e) => patchDraft((d) => { d.subject_matter = e.target.value; })} />
            </label>
            <label className="block text-sm">
              <span className="eyebrow mb-1 block">Business context</span>
              <textarea className="input min-h-28 w-full" value={draft.business_context}
                onChange={(e) => patchDraft((d) => { d.business_context = e.target.value; })} />
            </label>
            <div>
              <div className="eyebrow mb-1.5">Roles & KPIs</div>
              <div className="space-y-2">
                {draft.role_overview.map((r, i) => (
                  <div key={i} className="rounded-xl border border-line p-3">
                    <div className="grid gap-2 sm:grid-cols-2">
                      <input className="input text-sm" value={r.role_title} placeholder="Role title"
                        onChange={(e) => patchDraft((d) => { d.role_overview[i].role_title = e.target.value; })} />
                      <input className="input text-sm" value={r.scope} placeholder="Scope"
                        onChange={(e) => patchDraft((d) => { d.role_overview[i].scope = e.target.value; })} />
                    </div>
                    {(r.kpi_tradeoffs ?? []).map((k, j) => (
                      <div key={j} className="mt-2 grid gap-2 sm:grid-cols-3">
                        <input className="input text-xs" value={k.metric} placeholder="KPI metric"
                          onChange={(e) => patchDraft((d) => { d.role_overview[i].kpi_tradeoffs![j].metric = e.target.value; })} />
                        <input className="input text-xs" value={k.target} placeholder="Target"
                          onChange={(e) => patchDraft((d) => { d.role_overview[i].kpi_tradeoffs![j].target = e.target.value; })} />
                        <input className="input text-xs" value={k.competing_pressure} placeholder="Competing pressure"
                          onChange={(e) => patchDraft((d) => { d.role_overview[i].kpi_tradeoffs![j].competing_pressure = e.target.value; })} />
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <button className="btn-primary" onClick={submitRevise} disabled={busy}>
                {busy ? "Regenerating…" : "Regenerate as new revision"}
              </button>
              <button className="btn-ghost" onClick={() => setEditing(false)} disabled={busy}>
                Cancel
              </button>
            </div>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
