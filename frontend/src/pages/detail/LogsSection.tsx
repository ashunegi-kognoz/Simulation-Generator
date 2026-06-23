import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../../api/client";
import type { LogsResponse } from "../../api/types";
import { Banner, Panel, Spinner, Stat } from "../../components/ui";
import { cn } from "../../lib/cn";

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const JOB_STYLE: Record<string, string> = {
  completed: "text-grass",
  running: "text-petrol",
  failed: "text-coral",
  queued: "text-muted",
};

export function LogsSection({
  simulationId,
  token,
}: {
  simulationId: string;
  token: string;
}) {
  const [data, setData] = useState<LogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true);
      try {
        const res = await api.getLogs(simulationId, token);
        setData(res);
        setError(null);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Couldn't load logs.");
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [simulationId, token],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // poll while the job is still running
  useEffect(() => {
    const running = data?.job?.status === "running" || data?.job?.status === "queued";
    if (running) {
      timer.current = window.setInterval(() => void load(true), 2000);
      return () => {
        if (timer.current) window.clearInterval(timer.current);
      };
    }
    if (timer.current) window.clearInterval(timer.current);
  }, [data?.job?.status, load]);

  const runs = data?.runs ?? [];
  const totalTokens = runs.reduce((sum, r) => sum + (r.tokens ?? 0), 0);
  const totalLatency = runs.reduce((sum, r) => sum + (r.latency_ms ?? 0), 0);

  return (
    <Panel
      eyebrow="API logs"
      title="Generation runs"
      right={
        <button className="btn-ghost h-8 px-3 text-xs" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      }
    >
      {loading && !data ? (
        <Spinner label="Loading logs…" />
      ) : error ? (
        <Banner tone="error" title="Couldn't load logs">{error}</Banner>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <Stat
              label="Job"
              value={
                <span className={cn(JOB_STYLE[data?.job?.status ?? ""] ?? "text-muted")}>
                  {data?.job?.status ?? "—"}
                </span>
              }
            />
            <Stat label="Runs" value={runs.length} />
            <Stat label="Tokens" value={totalTokens ? totalTokens.toLocaleString() : "—"} />
            <Stat label="Latency" value={totalLatency ? `${(totalLatency / 1000).toFixed(1)}s` : "—"} />
          </div>

          {data?.job?.status === "failed" && data.job.error && (
            <Banner tone="error" title="Job failed">{data.job.error}</Banner>
          )}

          {runs.length === 0 ? (
            <Banner tone="empty">
              No generation runs recorded yet. They appear here as the pipeline calls the model.
            </Banner>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left">
                    <th className="py-2 pr-3 font-medium text-muted">Stage</th>
                    <th className="py-2 pr-3 font-medium text-muted">Model</th>
                    <th className="py-2 pr-3 text-right font-medium text-muted">Tokens</th>
                    <th className="py-2 pr-3 text-right font-medium text-muted">Latency</th>
                    <th className="py-2 pl-3 text-right font-medium text-muted">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r, i) => (
                    <tr key={i} className="border-b border-line/60">
                      <td className="num py-2 pr-3 text-ink">{r.stage}</td>
                      <td className="py-2 pr-3 text-muted">{r.model ?? "—"}</td>
                      <td className="num py-2 pr-3 text-right text-muted">
                        {r.tokens != null ? r.tokens.toLocaleString() : "—"}
                      </td>
                      <td className="num py-2 pr-3 text-right text-muted">
                        {r.latency_ms != null ? `${r.latency_ms} ms` : "—"}
                      </td>
                      <td className="num py-2 pl-3 text-right text-faint">{fmtTime(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
