import { describe, expect, it } from "vitest";
import {
  BUDGET,
  distributeEven,
  emptyUnits,
  isBalanced,
  remainingUnits,
  totalUnits,
  withUnit,
} from "./allocation";

describe("allocation helpers", () => {
  it("starts empty with the full budget remaining", () => {
    const u = emptyUnits();
    expect(totalUnits(u)).toBe(0);
    expect(remainingUnits(u)).toBe(BUDGET);
    expect(isBalanced(u)).toBe(false);
  });

  it("is balanced only when the four values sum to exactly 100", () => {
    expect(isBalanced({ A: 40, B: 30, C: 20, D: 10 })).toBe(true);
    expect(isBalanced({ A: 40, B: 30, C: 20, D: 9 })).toBe(false); // 99
    expect(isBalanced({ A: 40, B: 30, C: 20, D: 11 })).toBe(false); // 101
  });

  it("rejects negative values", () => {
    expect(isBalanced({ A: 110, B: 0, C: 0, D: -10 })).toBe(false);
  });

  it("clamps a single option to 0..budget", () => {
    expect(withUnit(emptyUnits(), "A", 250).A).toBe(BUDGET);
    expect(withUnit(emptyUnits(), "A", -5).A).toBe(0);
    expect(withUnit(emptyUnits(), "B", 33.6).B).toBe(34);
  });

  it("distributes the budget evenly and stays balanced", () => {
    const u = distributeEven();
    expect(totalUnits(u)).toBe(BUDGET);
    expect(isBalanced(u)).toBe(true);
    expect(u).toEqual({ A: 25, B: 25, C: 25, D: 25 });
  });
});
