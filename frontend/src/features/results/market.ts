import { fmt0, fmt2 } from "@/lib/labels";
import type { MarketDistrict, MarketSummary } from "@/lib/types";

/** Plain facts about the extremes in the data; no judgement about which is the better choice. */
export function marketHighlights(market: MarketSummary): string[] {
  const counted = market.districts.filter((d) => d.competitors_per_km2 !== null);
  if (counted.length < 2) return [];
  const sorted = [...counted].sort(
    (a, b) => (a.competitors_per_km2 ?? 0) - (b.competitors_per_km2 ?? 0),
  );
  const low = sorted[0] as MarketDistrict;
  const high = sorted[sorted.length - 1] as MarketDistrict;
  return [
    `Najviše evidentiranih sličnih objekata po km²: ${high.name} (${fmt2(high.competitors_per_km2 ?? 0)}).`,
    `Najmanje: ${low.name} (${fmt2(low.competitors_per_km2 ?? 0)}).`,
  ];
}

/** "1 obavijest čeka", "14 obavijesti čeka" (Croatian plural after a number). */
export function pendingNotices(count: number): string {
  const one = count % 10 === 1 && count % 100 !== 11;
  return `${fmt0(count)} ${one ? "obavijest" : "obavijesti"} Grada čeka provjeru tima.`;
}

/** The districts the user chose, in the same terms as the extremes; nothing is judged. */
export function chosenDistricts(market: MarketSummary, ids: string[]): string[] {
  return market.districts
    .filter((d) => ids.includes(d.district_id) && d.competitors_per_km2 !== null)
    .map(
      (d) =>
        `Vaš odabir, ${d.name}: ${fmt0(d.competitors ?? 0)} sličnih objekata, ${fmt2(d.competitors_per_km2 ?? 0)} po km².`,
    );
}
