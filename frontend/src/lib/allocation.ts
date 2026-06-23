import type { Letter, LetterUnits } from "../api/types";
import { LETTERS } from "../api/types";

/** Every decision distributes exactly this many units across the four options. */
export const BUDGET = 100;

export function emptyUnits(): LetterUnits {
  return { A: 0, B: 0, C: 0, D: 0 };
}

export function totalUnits(units: LetterUnits): number {
  return LETTERS.reduce((sum, l) => sum + (units[l] || 0), 0);
}

export function remainingUnits(units: LetterUnits, budget = BUDGET): number {
  return budget - totalUnits(units);
}

/** Balanced means the four non-negative values sum to exactly the budget. */
export function isBalanced(units: LetterUnits, budget = BUDGET): boolean {
  return (
    LETTERS.every((l) => Number.isInteger(units[l]) && units[l] >= 0) &&
    totalUnits(units) === budget
  );
}

/** Immutably set one option's units, clamped to 0..budget. */
export function withUnit(
  units: LetterUnits,
  letter: Letter,
  value: number,
  budget = BUDGET,
): LetterUnits {
  const clamped = Math.max(0, Math.min(budget, Math.round(value || 0)));
  return { ...units, [letter]: clamped };
}

/** Split the budget as evenly as possible (remainder lands on the first options). */
export function distributeEven(budget = BUDGET): LetterUnits {
  const base = Math.floor(budget / LETTERS.length);
  let remainder = budget - base * LETTERS.length;
  const out = emptyUnits();
  for (const l of LETTERS) {
    out[l] = base + (remainder > 0 ? 1 : 0);
    if (remainder > 0) remainder -= 1;
  }
  return out;
}
