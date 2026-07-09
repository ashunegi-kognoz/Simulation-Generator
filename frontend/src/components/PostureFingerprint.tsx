import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";
import type { PostureFingerprint as Fingerprint } from "../api/types";
import { Stat } from "./ui";

const FALLBACK_COLORS = ["#2F6BD6", "#15A06A", "#C98A00", "#5A6675"];
const POSTURE_COLOR: Record<string, string> = {
  Protect: "#2F6BD6",
  Enable: "#15A06A",
  Hybrid: "#7C58D6",
  Defer: "#C77F0A",
};

const pct = (n: number) => `${Math.round(n * 100)}%`;

export function PostureFingerprintView({ fingerprint }: { fingerprint: Fingerprint }) {
  const keys = Object.keys(fingerprint.overall);
  const radarData = keys.map((p) => ({
    posture: p,
    share: Math.round((fingerprint.overall[p] ?? 0) * 100),
  }));

  // overall[key] == *_index for canonical sims and is defined for dynamic ones too.
  const indices: { posture: string; value: number }[] = keys.map((p) => ({
    posture: p,
    value: fingerprint.overall[p] ?? 0,
  }));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <div className="eyebrow mb-2">Posture mix</div>
        <div className="h-[240px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData} outerRadius="72%">
              <PolarGrid stroke="#D7DEE7" />
              <PolarAngleAxis
                dataKey="posture"
                tick={{ fill: "#5A6675", fontSize: 12 }}
              />
              <Radar
                dataKey="share"
                stroke="#0B6E63"
                fill="#0B6E63"
                fillOpacity={0.18}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <div className="eyebrow mb-3">Posture indices</div>
        <div className="space-y-3">
          {indices.map((row, i) => (
            <div key={row.posture}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-medium text-ink">{row.posture}</span>
                <span className="num text-muted">{pct(row.value)}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-canvas">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.max(0, Math.min(100, row.value * 100))}%`,
                    backgroundColor: POSTURE_COLOR[row.posture] ?? FALLBACK_COLORS[i % FALLBACK_COLORS.length],
                  }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          <Stat label="Decisiveness" value={pct(fingerprint.decisiveness)} />
          <Stat label="Consistency" value={pct(fingerprint.consistency)} />
          <Stat label="Dim. sensitivity" value={pct(fingerprint.dimension_sensitivity)} />
          <Stat label="Reliability" value={fingerprint.reliability} />
          <Stat label="Decisions" value={fingerprint.n_decisions} />
        </div>
      </div>
    </div>
  );
}
