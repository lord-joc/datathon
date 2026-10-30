import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BasisConflict, DistrictLayer, RankingItem, SpaceSummary, Status } from "@/lib/types";

import { BasisDialog } from "./BasisDialog";
import { budgetFit, mapSpaces, strengths } from "./model";

const status = { candidate_status: "conditional" } as Status;

const item = (id: string, rank: number | null, point: [number, number] | null): RankingItem => ({
  space_id: id,
  candidate_status: "conditional",
  rank,
  score: rank === null ? null : 80,
  reason: null,
  reasons: [],
  raw_metrics: {},
  utilities: { transit: 0.9, area: 0.95, street: 0.4 },
  contributions: { transit: 30, area: 25, street: 5 },
  status_snapshot: status,
  coordinate_snapshot: {
    geometry: point ? { type: "Point", coordinates: point } : null,
    precision_status: point ? "building_approximate" : "missing",
    reason: point ? null : "missing_coordinate",
    geo_evidence_id: null,
    checked_at: null,
  },
});

describe("strengths", () => {
  it("names the strongest criteria, not weak ones", () => {
    expect(strengths(item("1", 1, [16, 45.8]), ["transit", "area", "street"])).toBe(
      "Prednosti: blizu javnog prijevoza i površina blizu ciljne.",
    );
  });
});

describe("mapSpaces", () => {
  const districts: DistrictLayer = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "d1",
        geometry: { type: "Polygon", coordinates: [] },
        properties: { district_id: "d1", name: "Sesvete", label_point: [16.1, 45.83] },
      },
    ],
  };
  const summary = (id: string, district: string | null) =>
    ({ space_id: id, address: "VATROGASNA 0000/BB", district_id: district }) as SpaceSummary;

  it("places unknown locations inside their district and counts the rest as hidden", () => {
    const index = new Map([
      ["2", summary("2", "d1")],
      ["3", summary("3", "d1")],
      ["4", summary("4", null)],
    ]);
    const out = mapSpaces(
      [item("1", 1, [15.97, 45.81]), item("2", 2, null), item("3", 3, null), item("4", 4, null)],
      index,
      districts,
    );
    expect(out.spaces.map((s) => s.kind)).toEqual(["building", "district", "district"]);
    expect(out.districtOnly).toBe(2);
    expect(out.hidden).toBe(1);
    // Two unknown spaces in one district do not overlap.
    expect(out.spaces[1]?.lon).not.toBe(out.spaces[2]?.lon);
    expect(out.spaces[1]?.label).toContain("samo četvrt");
  });
});

describe("BasisDialog", () => {
  const conflict: BasisConflict = {
    missing_by_space: { "5340": ["transit", "parking"], "5341": ["transit", "parking"] },
    partial_criteria: ["transit", "parking"],
    proposed_criteria: ["area", "street"],
    options: ["common_criteria", "remove_incomplete"],
    comparison_basis_token: "token-token-token-token",
    expires_in_s: 600,
  };

  it("preselects nothing and confirms only the user's choice", () => {
    const onConfirm = vi.fn();
    render(
      <BasisDialog
        conflict={conflict}
        total={186}
        busy={false}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    const radios = screen.getAllByRole("radio");
    expect(radios.every((r) => !(r as HTMLInputElement).checked)).toBe(true);
    const confirm = screen.getByRole("button", { name: /potvrdi/i });
    expect(confirm).toBeDisabled();
    expect(screen.getByText(/Za 2 od 186 prostora/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /ukloni 2 nepotpunih/i }));
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith("remove_incomplete");
  });
});

describe("budgetFit", () => {
  const priced = (value: number | null): RankingItem => ({
    ...item("9", 1, [16, 45.8]),
    raw_metrics: {
      cost: {
        value,
        unit: "eur_month",
        reason: value === null ? "cost_not_configured" : null,
        source_version_ids: [],
        detail: {},
      },
    },
  });

  it("compares only a known monthly price", () => {
    expect(budgetFit(priced(900), 1000)).toBe("within");
    expect(budgetFit(priced(1000), 1000)).toBe("within");
    expect(budgetFit(priced(1100), 1000)).toBe("over");
  });

  it("keeps an unknown price unknown instead of treating it as free", () => {
    expect(budgetFit(priced(null), 1000)).toBe("unknown");
    expect(budgetFit(item("8", 1, null), 1000)).toBe("unknown");
  });
});
