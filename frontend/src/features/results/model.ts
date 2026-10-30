import { useQuery } from "@tanstack/react-query";

import type { MapSpace } from "@/features/map/SpaceMap";
import { CRITERION_LABEL, CRITERION_STRENGTH, prettyAddress } from "@/lib/labels";
import { fetchAllSpaces } from "@/lib/queries";
import {
  CRITERIA,
  type Criterion,
  type DistrictLayer,
  type ProfileCode,
  type RankingItem,
  type SpaceSummary,
} from "@/lib/types";

/** Address, district and area for ranked ids (the snapshot stores only ids and metrics). */
export function useSpaceIndex(profile: ProfileCode | undefined) {
  return useQuery({
    queryKey: ["space-index", profile],
    queryFn: async ({ signal }) => {
      const { items } = await fetchAllSpaces(
        {
          profile: profile as ProfileCode,
          areaMin: null,
          areaMax: null,
          districtIds: [],
          includeConditional: true,
        },
        signal,
      );
      return new Map(items.map((s) => [s.space_id, s]));
    },
    enabled: profile !== undefined,
    staleTime: 5 * 60_000,
  });
}

export interface Groups {
  ready: RankingItem[];
  conditional: RankingItem[];
  unranked: RankingItem[];
}

export function groupItems(items: RankingItem[]): Groups {
  const byRank = (a: RankingItem, b: RankingItem) => (a.rank ?? 0) - (b.rank ?? 0);
  return {
    ready: items.filter((i) => i.rank !== null && i.candidate_status === "ready").sort(byRank),
    conditional: items
      .filter((i) => i.rank !== null && i.candidate_status === "conditional")
      .sort(byRank),
    unranked: items.filter((i) => i.rank === null),
  };
}

const join = (parts: string[]) =>
  parts.length <= 1 ? (parts[0] ?? "") : `${parts.slice(0, -1).join(", ")} i ${parts.at(-1)}`;

/** "Prednosti: blizu javnog prijevoza i ulični položaj." from the strongest contributions. */
export function strengths(item: RankingItem, used: Criterion[]): string {
  const top = used
    .filter((c) => (item.utilities[c] ?? 0) >= 0.7 && (item.contributions[c] ?? 0) > 0)
    .sort((a, b) => (item.contributions[b] ?? 0) - (item.contributions[a] ?? 0))
    .slice(0, 3)
    .map((c) => CRITERION_STRENGTH[c]);
  return top.length ? `Prednosti: ${join(top)}.` : "Nema izrazitih prednosti.";
}

export function weaknesses(item: RankingItem, used: Criterion[]): string | null {
  const low = used
    .filter((c) => (item.utilities[c] ?? 1) < 0.3)
    .slice(0, 2)
    .map((c) => CRITERION_LABEL[c].toLocaleLowerCase("hr"));
  return low.length ? `Slabije: ${join(low)}.` : null;
}

export const orderedCriteria = (used: Criterion[]) => CRITERIA.filter((c) => used.includes(c));

/**
 * Map positions: the snapshot coordinate when known, otherwise a point inside the space's
 * district, drawn as "district only" (team decision ADR20).
 */
export function mapSpaces(
  items: RankingItem[],
  index: Map<string, SpaceSummary> | undefined,
  districts: DistrictLayer | undefined,
): { spaces: MapSpace[]; districtOnly: number; hidden: number } {
  const labelPoint = new Map(
    (districts?.features ?? []).map((f) => [f.properties.district_id, f.properties.label_point]),
  );
  const spaces: MapSpace[] = [];
  let districtOnly = 0;
  let hidden = 0;
  const stacked = new Map<string, number>();
  for (const item of items) {
    const summary = index?.get(item.space_id);
    const address = summary ? prettyAddress(summary.address) : `Prostor ${item.space_id}`;
    const label = `${item.rank !== null ? `${item.rank}. ` : ""}${address}`;
    const geometry = item.coordinate_snapshot.geometry;
    if (geometry) {
      const [lon, lat] = geometry.coordinates;
      spaces.push({
        id: item.space_id,
        label: `${label}, približna lokacija zgrade`,
        rank: item.rank,
        lon,
        lat,
        kind:
          item.coordinate_snapshot.precision_status === "entrance_confirmed"
            ? "entrance"
            : "building",
      });
      continue;
    }
    const point = summary?.district_id ? labelPoint.get(summary.district_id) : undefined;
    if (point && summary?.district_id) {
      districtOnly += 1;
      // Several unknown spaces in one district sit side by side, not on top of each other.
      const nth = stacked.get(summary.district_id) ?? 0;
      stacked.set(summary.district_id, nth + 1);
      spaces.push({
        id: item.space_id,
        label: `${label}, točna lokacija nepoznata, prikazana je samo četvrt`,
        rank: item.rank,
        lon: point[0] + nth * 0.004,
        lat: point[1],
        kind: "district",
      });
    } else {
      hidden += 1;
    }
  }
  return { spaces, districtOnly, hidden };
}

export type BudgetFit = "within" | "over" | "unknown";

/** Compares only a known monthly price (eur_month) with the budget; unknown stays unknown. */
export function budgetFit(item: RankingItem, budget: number): BudgetFit {
  const cost = item.raw_metrics.cost;
  if (!cost || cost.value === null || cost.unit !== "eur_month") return "unknown";
  return cost.value <= budget ? "within" : "over";
}
