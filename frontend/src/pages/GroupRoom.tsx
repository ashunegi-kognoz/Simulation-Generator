import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { GroupAnalytics, Posture, PostureUnits } from "../api/types";
import { POSTURES } from "../api/types";
import { GroupCharts } from "../components/GroupCharts";
import { Banner, Panel, Spinner } from "../components/ui";
import { BUDGET } from "../lib/allocation";

const POSTURE_COLOR: Record<Posture, string> = {
  Protect: "#2F6BD6",
  Enable: "#15A06A",
  Hybrid: "#7C58D6",
  Defer: "#C77F0A",
};

function emptyPostureUnits(): PostureUnits {
  return { Protect: 0, Enable: 0, Hybrid: 0, Defer: 0 };
}
function postureTotal(u: PostureUnits): number {
  return POSTURES.reduce((s, p) => s + (u[p] || 0), 0);
}
function postureBalanced(u: PostureUnits): boolean {
  return POSTURES.every((p) => u[p] >= 0) && postureTotal(u) === BUDGET;
}

interface Row {
  decision_number: number;
  units: PostureUnits;
}

export function GroupRoom({
  token,
  initialTeamId,
}: {
  token: string;
  initialTeamId?: string;
}) {
  const [teamId, setTeamId] = useState(initialTeamId ?? "");
  const [rows, setRows] = useState<Row[]>([{ decision_number: 1, units: emptyPostureUnits() }]);
  const [analytics, setAnalytics] = useState<GroupAnalytics | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allBalanced = rows.every((r) => postureBalanced(r.units));

  function setUnit(i: number, posture: Posture, value: number) {
    const clamped = Math.max(0, Math.min(BUDGET, Math.round(value || 0)));
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, units: { ...r.units, [posture]: clamped } } : r)));
  }

  async function reconcile() {
    if (!token) return setError("Your session expired. Please sign in again.");
    if (!teamId) return setError("Enter a team id.");
    setBusy(true);
    setError(null);
    try {
      const res = await api.reconcileTeam(
        teamId,
        token,
        rows.map((r) => ({ decision_number: r.decision_number, units: r.units })),
      );
      setAnalytics(res.analytics);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Reconcile failed.");
    } finally {
      setBusy(false);
    }
  }

  async function loadAnalytics() {
    if (!token || !teamId) return setError("Enter a tenant and team id.");
    setBusy(true);
    setError(null);
    try {
      const res = await api.getTeamAnalytics(teamId, token);
      setAnalytics(res.analytics);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No analytics found for this team yet.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
      <Panel eyebrow="Group room" title="Reconcile the team allocation">
        <div className="space-y-4">
          <Banner tone="info">
            Enter the team's agreed split per decision. Members' individual sessions are read
            automatically as the pre-discussion baseline. Stances are named here because this is the
            facilitator's view.
          </Banner>

          <div>
            <label className="label">Team id</label>
            <input className="input num" value={teamId} onChange={(e) => setTeamId(e.target.value.trim())} placeholder="team UUID" />
          </div>

          <div className="space-y-3">
            {rows.map((r, i) => {
              const total = postureTotal(r.units);
              const remaining = BUDGET - total;
              return (
                <div key={i} className="rounded-xl border border-line p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="num text-sm font-medium text-ink">Decision {r.decision_number}</span>
                    <span
                      className={`num text-xs font-medium ${
                        remaining === 0 ? "text-grass" : remaining < 0 ? "text-coral" : "text-amber"
                      }`}
                    >
                      {remaining === 0 ? "Balanced" : remaining < 0 ? `Over by ${-remaining}` : `${remaining} left`}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                    {POSTURES.map((p) => (
                      <div key={p}>
                        <div className="mb-1 flex items-center gap-1.5">
                          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: POSTURE_COLOR[p] }} />
                          <span className="text-[11px] text-muted">{p}</span>
                        </div>
                        <input
                          type="number"
                          min={0}
                          max={BUDGET}
                          className="input num py-1.5"
                          value={r.units[p]}
                          onChange={(e) => setUnit(i, p, parseInt(e.target.value || "0", 10))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between">
            <button
              className="text-xs font-medium text-petrol hover:text-petrol-hover"
              onClick={() =>
                setRows((rs) => [...rs, { decision_number: rs.length + 1, units: emptyPostureUnits() }])
              }
            >
              + Add decision
            </button>
            {rows.length > 1 && (
              <button
                className="text-xs font-medium text-coral"
                onClick={() => setRows((rs) => rs.slice(0, -1))}
              >
                Remove last
              </button>
            )}
          </div>

          {error && <Banner tone="error">{error}</Banner>}

          <div className="flex flex-wrap items-center gap-3">
            <button className="btn-primary" onClick={reconcile} disabled={busy || !allBalanced}>
              Reconcile and compute
            </button>
            <button className="btn-ghost" onClick={loadAnalytics} disabled={busy}>
              Load saved analytics
            </button>
            {busy && <Spinner />}
            {!allBalanced && <span className="text-sm text-muted">Each decision must total 100.</span>}
          </div>
        </div>
      </Panel>

      <Panel eyebrow="Analytics" title="Group pattern">
        {!analytics && !busy && (
          <Banner tone="empty">Reconcile a team, or load previously computed analytics.</Banner>
        )}
        {analytics && <GroupCharts analytics={analytics} />}
      </Panel>
    </div>
  );
}
