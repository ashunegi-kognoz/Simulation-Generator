import { useEffect, useState } from "react";
import { ApiError, api } from "../../api/client";
import type { MappingResponse } from "../../api/types";
import { Banner, Panel, Spinner } from "../../components/ui";

const BAND_LABEL: Record<string, string> = {
  mid: "Mid",
  senior: "Senior",
  exec: "Exec",
  c_suite: "C-suite",
};

export function MappingSection({
  simulationId,
  token,
  onOpenSession,
  onReconcile,
}: {
  simulationId: string;
  token: string;
  onOpenSession: (ref: string) => void;
  onReconcile: (teamId: string, teamName: string) => void;
}) {
  const [data, setData] = useState<MappingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .getMapping(simulationId, token)
      .then((res) => alive && setData(res))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : "Couldn't load mapping."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [simulationId, token]);

  if (loading) {
    return (
      <Panel eyebrow="User & group mapping" title="Participants">
        <Spinner label="Loading participants…" />
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel eyebrow="User & group mapping" title="Participants">
        <Banner tone="error" title="Couldn't load mapping">{error}</Banner>
      </Panel>
    );
  }
  if (!data || data.participants.length === 0) {
    return (
      <Panel eyebrow="User & group mapping" title="Participants">
        <Banner tone="empty">
          No participants yet. They're created when the simulation generates — check back once it's
          ready.
        </Banner>
      </Panel>
    );
  }

  return (
    <div className="space-y-6">
      <Panel
        eyebrow="User & group mapping"
        title={`Participants (${data.participants.length})`}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="py-2 pr-3 font-medium text-muted">User</th>
                <th className="py-2 pr-3 font-medium text-muted">Role</th>
                <th className="py-2 pr-3 font-medium text-muted">Function</th>
                <th className="py-2 pr-3 font-medium text-muted">Entity</th>
                <th className="py-2 pr-3 font-medium text-muted">Seniority</th>
                <th className="py-2 pl-3 text-right font-medium text-muted">Session</th>
              </tr>
            </thead>
            <tbody>
              {data.participants.map((p) => (
                <tr key={p.ref} className="border-b border-line/60">
                  <td className="num py-2.5 pr-3 font-semibold text-ink">{p.ref}</td>
                  <td className="py-2.5 pr-3 text-ink">{p.role_title ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-muted">{p.function ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-muted">{p.entity ?? "—"}</td>
                  <td className="py-2.5 pr-3 text-muted">
                    {p.seniority_band ? BAND_LABEL[p.seniority_band] ?? p.seniority_band : "—"}
                  </td>
                  <td className="py-2.5 pl-3 text-right">
                    <button
                      className="text-xs font-medium text-petrol hover:text-petrol-hover"
                      onClick={() => onOpenSession(p.ref)}
                    >
                      Open session →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-faint">
          "Open session" launches the participant runtime for that person (postures stay hidden).
        </p>
      </Panel>

      <Panel eyebrow="Group rounds" title={`Teams (${data.teams.length})`}>
        {data.teams.length === 0 ? (
          <Banner tone="empty">This simulation has no group rounds, so there are no teams.</Banner>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {data.teams.map((t) => (
              <div key={t.id} className="rounded-xl border border-line p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium text-ink">{t.name}</div>
                    <div className="eyebrow mt-0.5">Round {t.round_index}</div>
                  </div>
                  <button
                    className="btn-ghost h-8 px-3 text-xs"
                    onClick={() => onReconcile(t.id, t.name)}
                  >
                    Reconcile →
                  </button>
                </div>
                <div className="num mt-3 flex flex-wrap gap-1.5">
                  {t.members.map((m) => (
                    <span
                      key={m}
                      className="rounded-md bg-canvas px-2 py-0.5 text-xs font-medium text-ink"
                    >
                      {m}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
