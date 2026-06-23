import { useEffect, useState } from "react";
import { ApiError, api } from "../../api/client";
import type {
  Posture,
  SimContent,
  SimContentDecision,
} from "../../api/types";
import { Banner, Panel, Spinner } from "../../components/ui";
import { cn } from "../../lib/cn";

const POSTURE_STYLE: Record<Posture, string> = {
  Protect: "bg-petrol-soft text-petrol",
  Enable: "bg-grass-soft text-grass",
  Hybrid: "bg-amber-soft text-amber",
  Defer: "bg-canvas text-muted",
};

function PostureTag({ posture }: { posture: Posture }) {
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", POSTURE_STYLE[posture])}>
      {posture}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{value || "—"}</p>
    </div>
  );
}

function DecisionBoard({ decisions }: { decisions: SimContentDecision[] }) {
  return (
    <div className="space-y-3">
      {decisions.map((d) => (
        <div key={d.decision_number} className="rounded-xl border border-line bg-canvas p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-ink">
              <span className="num text-muted">D{d.decision_number}</span> · {d.title}
            </div>
            <span className="rounded-full bg-panel px-2 py-0.5 text-[11px] font-medium text-ink">
              {d.dimension}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted">{d.question}</p>
          <div className="mt-3 space-y-2">
            {d.options.map((o, i) => (
              <div key={i} className="rounded-lg border border-line bg-panel px-3 py-2">
                <div className="mb-0.5 flex items-center gap-2">
                  <span className="num text-xs font-semibold text-ink">{o.label}</span>
                  <PostureTag posture={o.posture} />
                </div>
                <p className="text-sm text-ink">{o.content}</p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function RoundBlock({ roundKey, round }: { roundKey: string; round: SimContent["rounds"][string] }) {
  const num = roundKey.replace("round_", "");
  return (
    <Panel
      eyebrow={`Round ${num}`}
      title={round.round_type === "group" ? "Group round" : "Individual round"}
    >
      {round.participants && (
        <div className="space-y-4">
          {Object.entries(round.participants).map(([pid, p]) => (
            <div key={pid} className="rounded-xl border border-line p-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="num rounded-md bg-ink px-2 py-0.5 text-xs font-semibold text-white">
                  {pid}
                </span>
                <span className="text-sm font-medium text-ink">Participant view</span>
              </div>
              <div className="space-y-3">
                <Field label="Role" value={p.role_data} />
                <Field label="Your situation" value={p.situation_data} />
                <div>
                  <div className="eyebrow mb-1.5">Decision board</div>
                  <DecisionBoard decisions={p.decision_board} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {round.teams && (
        <div className="space-y-4">
          {Object.entries(round.teams).map(([tid, t]) => (
            <div key={tid} className="rounded-xl border border-line p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-ink px-2 py-0.5 text-xs font-semibold text-white">
                  {t.team_name}
                </span>
                <span className="num text-xs text-muted">{t.participant_ids.join(", ")}</span>
              </div>
              <Field label="Scenario" value={t.scenario_data} />
              <div className="mt-4 space-y-4">
                {Object.entries(t.members).map(([pid, m]) => (
                  <div key={pid} className="rounded-xl border border-line bg-canvas p-3">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="num rounded-md bg-panel px-2 py-0.5 text-xs font-semibold text-ink">
                        {pid}
                      </span>
                      <span className="text-xs text-muted">member view</span>
                    </div>
                    <Field label="Your situation" value={m.situation_data} />
                    <div className="mt-3">
                      <div className="eyebrow mb-1.5">Decision board</div>
                      <DecisionBoard decisions={m.decision_board} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function EntriesSection({
  simulationId,
  token,
}: {
  simulationId: string;
  token: string;
}) {
  const [content, setContent] = useState<SimContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .getContent(simulationId, token)
      .then((res) => {
        if (alive) setContent(res.sim_data);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : "Couldn't load content.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [simulationId, token]);

  if (loading) {
    return (
      <Panel eyebrow="Simulation entries" title="Generated content">
        <Spinner label="Loading generated content…" />
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel eyebrow="Simulation entries" title="Generated content">
        <Banner tone="error" title="Couldn't load content">{error}</Banner>
      </Panel>
    );
  }
  if (!content) {
    return (
      <Panel eyebrow="Simulation entries" title="Generated content">
        <Banner tone="empty">
          No generated content yet. Once the simulation finishes generating, every participant and
          team's content appears here.
        </Banner>
      </Panel>
    );
  }

  const c = content.common_data;
  return (
    <div className="space-y-6">
      <Panel eyebrow="Common to all participants" title="Shared world">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Allocation Room" value={c.allocation_room_data} />
          <Field label="Business landscape" value={c.business_landscape} />
          <div>
            <div className="eyebrow mb-1">Business priorities</div>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-ink">
              {c.business_priorities.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ol>
          </div>
          <Field label="Crisis" value={c.crisis_data} />
          <Field label="Reflection board support" value={c.reflection_board_helping_data} />
        </div>
      </Panel>

      {Object.entries(content.rounds).map(([k, r]) => (
        <RoundBlock key={k} roundKey={k} round={r} />
      ))}
    </div>
  );
}
