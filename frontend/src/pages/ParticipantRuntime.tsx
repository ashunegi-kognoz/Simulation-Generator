import { useMemo, useState } from "react";
import { ApiError, api } from "../api/client";
import type { Letter, LetterUnits, ReflectionBoardResponse, RenderedSession } from "../api/types";
import { AllocationMeter } from "../components/AllocationMeter";
import { Banner, Panel, Spinner } from "../components/ui";
import { emptyUnits, isBalanced, withUnit } from "../lib/allocation";

type Phase = "open" | "allocate" | "board";

export function ParticipantRuntime({
  token,
  initialSimulationId,
  initialParticipantRef,
}: {
  token: string;
  initialSimulationId: string | null;
  initialParticipantRef?: string;
}) {
  const [phase, setPhase] = useState<Phase>("open");
  const [simulationId, setSimulationId] = useState(initialSimulationId ?? "");
  const [participantRef, setParticipantRef] = useState(initialParticipantRef ?? "p1");
  const [displaySeed, setDisplaySeed] = useState("");

  const [session, setSession] = useState<RenderedSession | null>(null);
  const [units, setUnits] = useState<Record<number, LetterUnits>>({});
  const [board, setBoard] = useState<ReflectionBoardResponse | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allBalanced = useMemo(
    () => !!session && session.decisions.every((d) => isBalanced(units[d.decision_number] ?? emptyUnits())),
    [session, units],
  );

  async function open() {
    if (!token) return setError("Your session expired. Please sign in again.");
    if (!simulationId) return setError("Enter a simulation id.");
    setBusy(true);
    setError(null);
    try {
      const created = await api.createSession(token, {
        simulation_id: simulationId,
        participant_ref: participantRef,
        display_seed: displaySeed ? parseInt(displaySeed, 10) : undefined,
      });
      const s = await api.getSession(created.session_id, token);
      setSession(s);
      const init: Record<number, LetterUnits> = {};
      s.decisions.forEach((d) => (init[d.decision_number] = emptyUnits()));
      setUnits(init);
      setPhase("allocate");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't open the session.");
    } finally {
      setBusy(false);
    }
  }

  function setUnit(decision: number, letter: Letter, value: number) {
    setUnits((u) => ({ ...u, [decision]: withUnit(u[decision] ?? emptyUnits(), letter, value) }));
  }

  async function submitAllocations() {
    if (!session || !allBalanced) return;
    setBusy(true);
    setError(null);
    try {
      await api.submitAllocations(
        session.session_id,
        token,
        session.decisions.map((d) => ({ decision_number: d.decision_number, units: units[d.decision_number] })),
      );
      // Straight to the Reflection Board: the board is computed deterministically
      // from the allocations just submitted -- no interstitial step.
      const b = await api.getReflection(session.session_id, token);
      setBoard(b);
      setPhase("board");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Submission failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {phase === "open" && (
        <Panel eyebrow="Participant runtime" title="Open a session">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Simulation id" value={simulationId} onChange={setSimulationId} mono />
            <Field label="Participant" value={participantRef} onChange={setParticipantRef} mono />
            <Field label="Display seed (optional)" value={displaySeed} onChange={setDisplaySeed} mono />
          </div>
          {error && <div className="mt-4"><Banner tone="error">{error}</Banner></div>}
          <div className="mt-5 flex items-center gap-3">
            <button className="btn-primary" onClick={open} disabled={busy}>
              {busy ? "Opening…" : "Open session"}
            </button>
            {busy && <Spinner />}
          </div>
          <p className="mt-3 text-xs text-muted">
            You'll see four options per decision, labelled A–D. The outcome parameter behind each
            option stays hidden while you allocate; your Reflection Board reveals the mapping.
          </p>
        </Panel>
      )}

      {phase === "allocate" && session && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <div className="eyebrow">Allocate</div>
              <h2 className="font-display text-xl text-ink">Distribute 100 units per decision</h2>
            </div>
            <span className={`num text-sm font-medium ${allBalanced ? "text-grass" : "text-amber"}`}>
              {session.decisions.filter((d) => isBalanced(units[d.decision_number] ?? emptyUnits())).length}
              /{session.decisions.length} balanced
            </span>
          </div>

          {session.decisions.map((d) => (
            <Panel key={d.decision_number} eyebrow={`Decision ${d.decision_number} · ${d.dimension}`} title={d.title}>
              <p className="mb-5 text-sm leading-relaxed text-muted">{d.question}</p>
              <AllocationMeter
                options={d.options}
                units={units[d.decision_number] ?? emptyUnits()}
                onChange={(letter, value) => setUnit(d.decision_number, letter, value)}
              />
            </Panel>
          ))}

          {error && <Banner tone="error">{error}</Banner>}
          <div className="flex items-center gap-3">
            <button className="btn-primary" onClick={submitAllocations} disabled={busy || !allBalanced}>
              {busy ? "Building your Reflection Board…" : "Submit allocations"}
            </button>
            {!allBalanced && (
              <span className="text-sm text-muted">Each decision must total exactly 100 to submit.</span>
            )}
          </div>
        </>
      )}

      {phase === "board" && board && (
        <>
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
            <Panel
              key={roundIndex}
              eyebrow={`Round ${roundIndex}`}
              title="Where your units went"
            >
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
                <div className="border-t border-line pt-3 text-xs text-muted">
                  <span className="num">{round.total_units}</span> units allocated this round. Shares
                  are your own allocation — every unit you placed on an option counted toward that
                  option's outcome parameter.
                </div>
              </div>
            </Panel>
          ))}

          {board.archetype && board.dominant_pattern && (
            <Panel eyebrow="Your leadership pattern" title={board.archetype.name}>
              <p className="mb-2 text-xs text-muted">
                Based on where you placed most of your units:{" "}
                {board.dominant_pattern.names.join(" + ")}
              </p>
              <p className="text-sm leading-relaxed text-ink">{board.archetype.description}</p>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className={`input ${mono ? "num" : ""}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
