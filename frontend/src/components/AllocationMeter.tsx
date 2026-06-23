import type { Letter, LetterUnits, RenderedOption } from "../api/types";
import { LETTERS } from "../api/types";
import { BUDGET, remainingUnits, totalUnits } from "../lib/allocation";
import { cn } from "../lib/cn";

// A monochrome petrol ramp distinguishes the four channels WITHOUT implying any
// posture — participants must never be able to infer Protect/Enable/Hybrid/Defer.
const CHANNEL_COLOR: Record<Letter, string> = {
  A: "#0B6E63",
  B: "#3E8E86",
  C: "#6FA9A3",
  D: "#A6C9C5",
};

export function AllocationMeter({
  options,
  units,
  onChange,
  disabled = false,
}: {
  options: RenderedOption[];
  units: LetterUnits;
  onChange: (letter: Letter, value: number) => void;
  disabled?: boolean;
}) {
  const total = totalUnits(units);
  const remaining = remainingUnits(units);
  const over = remaining < 0;
  const balanced = remaining === 0;

  const readoutTone = balanced
    ? "text-grass"
    : over
      ? "text-coral"
      : "text-amber";

  return (
    <div>
      {/* budget readout */}
      <div className="mb-3 flex items-end justify-between">
        <div className="eyebrow">Allocation · 100 units</div>
        <div className={cn("num text-sm font-medium", readoutTone)}>
          {balanced
            ? "Balanced · 0 left"
            : over
              ? `Over by ${Math.abs(remaining)}`
              : `${remaining} left`}
        </div>
      </div>

      {/* stacked budget bar */}
      <div
        className="mb-5 flex h-3 w-full overflow-hidden rounded-full bg-canvas ring-1 ring-inset ring-line"
        role="img"
        aria-label={`Allocated ${total} of ${BUDGET} units`}
      >
        {LETTERS.map((l) => {
          const pct = Math.max(0, Math.min(100, ((units[l] || 0) / BUDGET) * 100));
          return (
            <div
              key={l}
              style={{ width: `${pct}%`, backgroundColor: CHANNEL_COLOR[l] }}
              className="h-full transition-[width] duration-150"
            />
          );
        })}
        {over && <div className="h-full flex-1 bg-coral/60" />}
      </div>

      {/* channels */}
      <div className="space-y-3">
        {options.map((opt) => {
          const value = units[opt.letter] || 0;
          return (
            <div key={opt.letter} className="rounded-xl border border-line p-3 sm:p-4">
              <div className="flex items-start gap-3">
                <span
                  className="num mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg text-sm font-semibold text-white"
                  style={{ backgroundColor: CHANNEL_COLOR[opt.letter] }}
                >
                  {opt.letter}
                </span>
                <p className="flex-1 text-sm leading-relaxed text-ink">{opt.content}</p>
                <span className="num w-12 shrink-0 text-right text-base font-semibold text-ink">
                  {value}
                </span>
              </div>

              <div className="mt-3 flex items-center gap-3 pl-10">
                <input
                  type="range"
                  min={0}
                  max={BUDGET}
                  step={1}
                  value={value}
                  disabled={disabled}
                  onChange={(e) => onChange(opt.letter, Number(e.target.value))}
                  aria-label={`Units for option ${opt.letter}`}
                  className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-line accent-petrol"
                  style={{ accentColor: CHANNEL_COLOR[opt.letter] }}
                />
                <input
                  type="number"
                  min={0}
                  max={BUDGET}
                  value={value}
                  disabled={disabled}
                  onChange={(e) => onChange(opt.letter, Number(e.target.value))}
                  aria-label={`Exact units for option ${opt.letter}`}
                  className="num w-16 rounded-lg border border-line px-2 py-1 text-right text-sm focus:border-petrol focus:outline-none"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
