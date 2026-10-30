import { describe, expect, it } from "vitest";

import { CAFE_WEIGHTS } from "@/test/utils";

import {
  fromSearch,
  INITIAL,
  levelsFromWeights,
  toSearch,
  weightsFromLevels,
  type Levels,
} from "./store";

describe("importance levels", () => {
  it("maps profile weights to levels 0–3", () => {
    const levels = levelsFromWeights(CAFE_WEIGHTS);
    expect(levels.transit).toBe(3);
    expect(levels.area).toBe(2);
    expect(levels.parking).toBe(1);
    expect(levels.schools).toBe(0);
  });

  it("normalises custom levels to 100 and keeps the profile's cost share", () => {
    const w = weightsFromLevels({ ...levelsFromWeights(CAFE_WEIGHTS), transit: 0 }, CAFE_WEIGHTS);
    const total = Object.values(w).reduce((a, b) => a + b, 0);
    expect(w.cost).toBe(20);
    expect(w.transit).toBe(0);
    expect(total).toBeCloseTo(100, 1);
  });

  it("gives zero weights when every level is 0", () => {
    const zero = Object.fromEntries(Object.keys(CAFE_WEIGHTS).map((k) => [k, 0])) as Levels;
    const w = weightsFromLevels(zero, CAFE_WEIGHTS);
    expect(w.transit).toBe(0);
    expect(w.area).toBe(0);
  });
});

describe("URL state", () => {
  it("round-trips the guide filters", () => {
    const filters = {
      ...INITIAL,
      profile: "cafe" as const,
      targetArea: 75,
      limitRange: true,
      areaMin: 40,
      areaMax: 120,
      districtIds: ["00159", "00160"],
      radius: 1000 as const,
      budget: 1200,
      levels: { ...levelsFromWeights(CAFE_WEIGHTS), culture: 0 as const },
    };
    const parsed = fromSearch(toSearch(filters, 2));
    expect(parsed.step).toBe(2);
    expect(parsed.filters).toMatchObject({
      profile: "cafe",
      targetArea: 75,
      areaMin: 40,
      areaMax: 120,
      districtIds: ["00159", "00160"],
      radius: 1000,
      budget: 1200,
    });
    expect(parsed.filters.levels?.culture).toBe(0);
    expect(parsed.filters.levels?.transit).toBe(3);
  });

  it("ignores untrusted values", () => {
    expect(fromSearch(new URLSearchParams("djelatnost=casino&m2=-5")).filters).toEqual(INITIAL);
    const bad = fromSearch(new URLSearchParams("djelatnost=cafe&m2=abc&vaznost=t9&radijus=7"));
    expect(bad.filters.targetArea).toBeNull();
    expect(bad.filters.levels).toBeNull();
    expect(bad.filters.radius).toBe(500);
  });
});
