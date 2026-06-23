import { useMemo, useState } from "react";
import { ApiError, api } from "../api/client";
import type { DebriefResponse, Letter, LetterUnits, RenderedSession } from "../api/types";
import { AllocationMeter } from "../components/AllocationMeter";
import { PostureFingerprintView } from "../components/PostureFingerprint";
import { Banner, Panel, Spinner } from "../components/ui";
import { emptyUnits, isBalanced, withUnit } from "../lib/allocation";

type Phase = "open" | "allocate" | "reflect" | "debrief";

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
  const [reflection, setReflection] = useState({ considered_most: "", resisted: "", uncertain: "" });
  const [commitment, setCommitment] = useState({ action: "", share_with: "", by_when: "" });
  const [debrief, setDebrief] = useState<DebriefResponse | null>(null);

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
      setPhase("reflect");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Submission failed.");
    } finally {
      setBusy(false);
    }
  }

  async function submitReflectAndCommit() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const firstDecision = session.decisions[0]?.decision_number ?? 1;
      if (reflection.considered_most || reflection.resisted || reflection.uncertain) {
        await api.submitReflection(session.session_id, token, {
          decision_number: firstDecision,
          reflection,
        });
      }
      if (commitment.action && commitment.share_with && commitment.by_when) {
        await api.submitCommitment(session.session_id, token, commitment);
      }
      const d = await api.getDebrief(session.session_id, token);
      setDebrief(d);
      setPhase("debrief");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't generate the debrief.");
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
            You'll see four options per decision, labelled A–D. The stance behind each option stays
            hidden until your debrief.
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
              Submit allocations
            </button>
            {!allBalanced && (
              <span className="text-sm text-muted">Each decision must total exactly 100 to submit.</span>
            )}
          </div>
        </>
      )}

      {phase === "reflect" && session && (
        <Panel eyebrow="Reflect" title="Before your debrief">
          <div className="space-y-4">
            <p className="text-sm text-muted">Optional — a few words sharpen the debrief.</p>
            <Area label="What did you weigh most?" value={reflection.considered_most} onChange={(v) => setReflection((r) => ({ ...r, considered_most: v }))} />
            <Area label="What did you resist?" value={reflection.resisted} onChange={(v) => setReflection((r) => ({ ...r, resisted: v }))} />
            <Area label="Where are you still uncertain?" value={reflection.uncertain} onChange={(v) => setReflection((r) => ({ ...r, uncertain: v }))} />

            <div className="border-t border-line pt-4">
              <h3 className="eyebrow mb-3">Commitment (optional)</h3>
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Action you'll take" value={commitment.action} onChange={(v) => setCommitment((c) => ({ ...c, action: v }))} />
                <Field label="Share it with" value={commitment.share_with} onChange={(v) => setCommitment((c) => ({ ...c, share_with: v }))} />
                <Field label="By when" value={commitment.by_when} onChange={(v) => setCommitment((c) => ({ ...c, by_when: v }))} />
              </div>
            </div>

            {error && <Banner tone="error">{error}</Banner>}
            <button className="btn-primary" onClick={submitReflectAndCommit} disabled={busy}>
              {busy ? "Preparing debrief…" : "Generate debrief"}
            </button>
          </div>
        </Panel>
      )}

      {phase === "debrief" && debrief && (
        <>
          <Panel eyebrow="Debrief" title="Your posture fingerprint">
            <PostureFingerprintView fingerprint={debrief.fingerprint} />
          </Panel>
          <Panel eyebrow="Reading" title={debrief.debrief.pattern_summary}>
            <div className="space-y-4 text-sm leading-relaxed text-ink">
              <DebriefBlock label="Interpretation" body={debrief.debrief.interpretation} />
              <DebriefBlock label="Tension you navigated" body={debrief.debrief.tension_navigated} />
              <DebriefBlock label="Possible blind spot" body={debrief.debrief.blind_spot} />
              <DebriefBlock label="Carry it forward" body={debrief.debrief.transfer_prompt} />
              <div className="text-xs text-muted">
                Grounded in decisions{" "}
                <span className="num">{debrief.debrief.cited_decisions.join(", ")}</span>.
              </div>
            </div>
          </Panel>
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
function Area({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="label">{label}</label>
      <textarea className="input min-h-[64px] resize-y" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
function DebriefBlock({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <p>{body}</p>
    </div>
  );
}
