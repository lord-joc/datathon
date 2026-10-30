import { describe, expect, it } from "vitest";

import { metricValue, prettyAddress, spacesWord } from "./labels";
import type { Metric } from "./types";

const metric = (value: number | null, unit: Metric["unit"] = "m"): Metric => ({
  value,
  unit,
  reason: value === null ? "cost_not_configured" : null,
  source_version_ids: [],
  detail: {},
});

describe("prettyAddress", () => {
  it.each([
    ["DOLAC 0009", "Dolac 9"],
    ["TRG BANA J. JELAČIĆA 0005", "Trg Bana J. Jelačića 5"],
    ["ILICA 0012A", "Ilica 12a"],
    ["VATROGASNA 0000/BB", "Vatrogasna bb"],
    ["ULICA KRALJA ZVONIMIRA 0017", "Ulica Kralja Zvonimira 17"],
  ])("%s -> %s", (raw, pretty) => {
    expect(prettyAddress(raw)).toBe(pretty);
  });
});

describe("metricValue", () => {
  it("never shows an unknown value as zero", () => {
    expect(metricValue("cost", metric(null, "eur_month"))).toBe("Nepoznato");
    expect(metricValue("transit", undefined)).toBe("Nepoznato");
  });

  it("labels distances as air distance", () => {
    expect(metricValue("transit", metric(147))).toBe("147 m zračno");
    expect(metricValue("parking", metric(1250))).toBe("1,3 km zračno");
  });
});

it("uses the right word for counts", () => {
  expect(spacesWord(1)).toBe("prostor");
  expect(spacesWord(11)).toBe("prostora");
  expect(spacesWord(21)).toBe("prostor");
  expect(spacesWord(186)).toBe("prostora");
});
