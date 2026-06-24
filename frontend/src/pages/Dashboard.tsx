import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { SimulationListItem } from "../api/types";
import { Banner, Panel, Spinner, StatusBadge } from "../components/ui";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Dashboard({
  token,
  onOpen,
  onCreate,
}: {
  token: string;
  onOpen: (id: string) => void;
  onCreate: () => void;
}) {
  const [items, setItems] = useState<SimulationListItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) {
      setError("Your session expired. Please sign in again.");
      setItems(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.listSimulations(token);
      setItems(res.simulations);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load simulations.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="eyebrow mb-1">Workspace</div>
          <h1 className="font-display text-2xl text-ink">Simulations</h1>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost h-9 px-3 text-sm" onClick={() => void load()} disabled={loading}>
            Refresh
          </button>
          <button className="btn-primary h-9" onClick={onCreate}>
            + Create New Simulation
          </button>
        </div>
      </div>

      <Panel>
        {loading ? (
          <Spinner label="Loading simulations…" />
        ) : error ? (
          <Banner tone="error" title="Couldn't load simulations">{error}</Banner>
        ) : !items || items.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-10 text-center">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-canvas">
              <span className="num text-base font-bold text-muted">100</span>
            </div>
            <div>
              <div className="font-medium text-ink">No simulations yet</div>
              <p className="mt-1 text-sm text-muted">
                Create your first simulation to generate decision rooms for your participants.
              </p>
            </div>
            <button className="btn-primary mt-1" onClick={onCreate}>
              + Create New Simulation
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="py-2.5 pr-3 font-medium text-muted">Simulation name</th>
                  <th className="py-2.5 pr-3 font-medium text-muted">Date created</th>
                  <th className="py-2.5 pr-3 text-right font-medium text-muted">Total Participants</th>
                  <th className="py-2.5 pr-3 text-right font-medium text-muted">Rounds</th>
                  <th className="py-2.5 pl-3 text-right font-medium text-muted">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => onOpen(s.id)}
                    className="cursor-pointer border-b border-line/60 transition-colors hover:bg-canvas"
                  >
                    <td className="py-3 pr-3">
                      <div className="font-medium text-ink">{s.name}</div>
                      {/* <div className="num text-xs text-faint">{s.id.split("-")[0]}…</div> */}
                    </td>
                    <td className="py-3 pr-3 text-muted">{fmtDate(s.created_at)}</td>
                    <td className="num py-3 pr-3 text-right text-ink">{s.participant_count ?? "—"}</td>
                    <td className="num py-3 pr-3 text-right text-muted">{s.round_count}</td>
                    <td className="py-3 pl-3 text-right">
                      <StatusBadge status={s.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
