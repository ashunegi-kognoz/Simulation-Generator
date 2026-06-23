import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { SimulationListItem } from "../api/types";
import { Banner, Panel, Spinner } from "../components/ui";
import { LogsSection } from "./detail/LogsSection";

export function LogsPage({ token }: { token: string }) {
  const [sims, setSims] = useState<SimulationListItem[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .listSimulations(token)
      .then((res) => {
        if (!alive) return;
        setSims(res.simulations);
        if (res.simulations.length > 0) setSelected(res.simulations[0].id);
      })
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : "Couldn't load simulations."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [token]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="eyebrow mb-1">Monitoring</div>
          <h1 className="font-display text-2xl text-ink">API Logs</h1>
        </div>
        {sims && sims.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-muted">
            <span>Simulation</span>
            <select
              className="input w-64"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {sims.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {loading ? (
        <Panel>
          <Spinner label="Loading simulations…" />
        </Panel>
      ) : error ? (
        <Banner tone="error" title="Couldn't load simulations">{error}</Banner>
      ) : !sims || sims.length === 0 ? (
        <Panel>
          <Banner tone="empty">
            No simulations yet. Once you create one, its generation logs will be selectable here.
          </Banner>
        </Panel>
      ) : (
        <LogsSection key={selected} simulationId={selected} token={token} />
      )}
    </div>
  );
}
