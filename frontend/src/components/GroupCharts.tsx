import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { GroupAnalytics } from "../api/types";
import { Stat } from "./ui";

export function GroupCharts({ analytics }: { analytics: GroupAnalytics }) {
  const numbers = new Set<number>();
  Object.keys(analytics.per_decision_dispersion).forEach((k) => numbers.add(Number(k)));
  Object.keys(analytics.per_decision_movement).forEach((k) => numbers.add(Number(k)));
  const data = [...numbers]
    .sort((a, b) => a - b)
    .map((n) => ({
      decision: `D${n}`,
      Dispersion: round2(analytics.per_decision_dispersion[String(n)] ?? 0),
      Movement: round2(analytics.per_decision_movement[String(n)] ?? 0),
    }));

  return (
    <div>
      <div className="grid grid-cols-3 gap-2.5">
        <Stat label="Anchor" value={analytics.anchor_participant ?? "—"} />
        <Stat label="Biggest mover" value={analytics.biggest_mover ?? "—"} />
        <Stat label="Posture diversity" value={round2(analytics.posture_diversity)} />
      </div>

      <div className="eyebrow mb-2 mt-5">Per-decision dispersion vs. movement</div>
      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid stroke="#EAEEF3" vertical={false} />
            <XAxis dataKey="decision" tick={{ fill: "#5A6675", fontSize: 12 }} />
            <YAxis tick={{ fill: "#5A6675", fontSize: 12 }} />
            <Tooltip
              contentStyle={{
                borderRadius: 12,
                border: "1px solid #D7DEE7",
                fontSize: 12,
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="Dispersion" fill="#0B6E63" radius={[4, 4, 0, 0]} />
            <Bar dataKey="Movement" fill="#7C58D6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
