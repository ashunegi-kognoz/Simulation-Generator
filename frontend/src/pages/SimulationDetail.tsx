import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { SimulationDetailMeta, SimulationStatus } from "../api/types";
import { Banner, Panel, Spinner, StatusBadge } from "../components/ui";
import { cn } from "../lib/cn";
import { GroupRoom } from "./GroupRoom";
import { ParticipantRuntime } from "./ParticipantRuntime";
import { DetailsSettings } from "./detail/DetailsSettings";
import { EntriesSection } from "./detail/EntriesSection";
import { ImagesSection } from "./detail/ImagesSection";
import { MappingSection } from "./detail/MappingSection";

type SectionId = "settings" | "mapping" | "entries" | "images";
const SECTIONS: { id: SectionId; label: string }[] = [
  { id: "settings", label: "Details & Settings" },
  { id: "mapping", label: "User & Group Mapping" },
  { id: "entries", label: "Simulation Entries" },
  { id: "images", label: "Images" },
];

type Overlay =
  | { kind: "run"; participantRef: string }
  | { kind: "group"; teamId: string; teamName: string }
  | null;

export function SimulationDetail({
  simulationId,
  token,
  onBack,
}: {
  simulationId: string;
  token: string;
  onBack: () => void;
}) {
  const [meta, setMeta] = useState<SimulationDetailMeta | null>(null);
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<SectionId>("settings");
  const [overlay, setOverlay] = useState<Overlay>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const m = await api.getSimulation(simulationId, token);
      setMeta(m);
      setStatus(m.status);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load this simulation.");
    } finally {
      setLoading(false);
    }
  }, [simulationId, token]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      {/* breadcrumb + header */}
      <div>
        <button
          className="mb-3 text-sm font-medium text-muted hover:text-ink"
          onClick={onBack}
        >
          ← All simulations
        </button>

        {loading ? (
          <Panel>
            <Spinner label="Loading simulation…" />
          </Panel>
        ) : error ? (
          <Banner tone="error" title="Couldn't load simulation">{error}</Banner>
        ) : meta ? (
          <div className="panel flex flex-wrap items-start justify-between gap-4 p-5 sm:p-6">
            <div className="min-w-0">
              <div className="eyebrow mb-1">Simulation</div>
              <h1 className="font-display text-2xl text-ink">{meta.name}</h1>
              <div className="num mt-1 text-xs text-faint">{meta.id}</div>
            </div>
            <div className="flex items-center gap-3">
              {meta.version != null && (
                <span className="num rounded-lg border border-line bg-canvas px-2.5 py-1 text-xs text-muted">
                  v{meta.version}
                </span>
              )}
              {status && <StatusBadge status={status} />}
            </div>
          </div>
        ) : null}
      </div>

      {meta && !error && (
        <>
          {/* section nav */}
          <nav className="flex flex-wrap gap-1 rounded-xl border border-line bg-panel p-1">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setSection(s.id);
                  setOverlay(null);
                }}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  section === s.id ? "bg-ink text-white" : "text-muted hover:text-ink",
                )}
              >
                {s.label}
              </button>
            ))}
          </nav>

          {/* overlay (run / group), or the active section */}
          {overlay ? (
            <div>
              <button
                className="mb-3 text-sm font-medium text-muted hover:text-ink"
                onClick={() => setOverlay(null)}
              >
                ← Back to {SECTIONS.find((s) => s.id === section)?.label}
              </button>
              {overlay.kind === "run" ? (
                <ParticipantRuntime
                  token={token}
                  initialSimulationId={simulationId}
                  initialParticipantRef={overlay.participantRef}
                />
              ) : (
                <>
                  <div className="mb-4">
                    <Banner tone="info" title={`Reconciling ${overlay.teamName}`}>
                      The team id is pre-filled below. Enter the team's agreed posture split per
                      decision, then reconcile.
                    </Banner>
                  </div>
                  <GroupRoom token={token} initialTeamId={overlay.teamId} />
                </>
              )}
            </div>
          ) : (
            <>
              {section === "settings" && (
                <DetailsSettings meta={meta} token={token} onStatusChange={setStatus} />
              )}
              {section === "mapping" && (
                <MappingSection
                  simulationId={simulationId}
                  token={token}
                  onOpenSession={(participantRef) => setOverlay({ kind: "run", participantRef })}
                  onReconcile={(teamId, teamName) =>
                    setOverlay({ kind: "group", teamId, teamName })
                  }
                />
              )}
              {section === "entries" && (
                <EntriesSection simulationId={simulationId} token={token} />
              )}
              {section === "images" && (
                <ImagesSection simulationId={simulationId} token={token} />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
