import type { ReflectionBoardResponse } from "../api/types";
import { Panel } from "./ui";

/**
 * The Reflection Board, rendered from the payload of GET /sessions/{id}/reflection.
 *
 * Single source of truth for board content so the participant player and any
 * admin/preview view stay identical. Everything here is already computed
 * server-side (no AI at view time):
 *   - framework            : the teaching frame
 *   - rounds[].parameters  : per round, per outcome parameter -> raw units + presented score
 *   - rounds[].lean_summary: plain-English "you leaned most on X, least on Y"
 *   - archetype            : the one archetype matching the dominant allocation pattern
 */
export function ReflectionBoard({ board }: { board: ReflectionBoardResponse }) {
  return (
    <div className="space-y-6">
      {board.framework && (
        <Panel eyebrow="Reflection Board" title={board.framework.framework_name}>
          <div className="space-y-3 text-sm leading-relaxed text-ink">
            <p>{board.framework.framework_definition}</p>
            <div>
              <div className="eyebrow mb-1">The tension you navigated</div>
              <p className="text-muted">{board.framework.learning_tension}</p>
            </div>
          </div>
        </Panel>
      )}

      {Object.entries(board.rounds).map(([roundIndex, round]) => (
        <Panel key={roundIndex} eyebrow={`Round ${roundIndex}`} title="Where your units went">
          <div className="space-y-5">
            {board.outcome_parameters.map((p) => {
              const cell = round.parameters[p.key];
              if (!cell) return null;
              const pct = Math.round(cell.score * 100);
              return (
                <div key={p.key}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <span className="text-sm font-medium text-ink">{p.name}</span>
                    <span className="num text-sm text-ink">
                      {pct}%<span className="ml-2 text-xs text-muted">({cell.units} units)</span>
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-line/60">
                    <div className="h-full rounded-full bg-ink/70" style={{ width: `${pct}%` }} />
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted">{p.definition}</p>
                </div>
              );
            })}

            {round.lean_summary && (
              <div className="rounded-lg bg-paper px-3 py-2 text-sm text-ink">
                {round.lean_summary}
              </div>
            )}

            <div className="border-t border-line pt-3 text-xs text-muted">
              <span className="num">{round.total_units}</span> units allocated this round. Shares are
              your own allocation — every unit you placed on an option counted toward that option's
              outcome parameter.
            </div>
          </div>
        </Panel>
      ))}

      {/* Archetype: only present once a sim has been generated with the archetype
          stage. Older sims return null here and the panel simply doesn't render. */}
      {board.archetype && board.dominant_pattern && (
        <Panel eyebrow="Your leadership pattern" title={board.archetype.name}>
          <p className="mb-2 text-xs text-muted">
            Based on where you placed most of your units:{" "}
            {board.dominant_pattern.names.join(" + ")}
          </p>
          <p className="text-sm leading-relaxed text-ink">{board.archetype.description}</p>
        </Panel>
      )}
    </div>
  );
}