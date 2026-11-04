import { TrendingUp } from "lucide-react";

import { Skeleton } from "@/components/ui/States";
import { fmt0, fmt2 } from "@/lib/labels";
import { useMarket } from "@/lib/queries";
import type { ProfileCode, RentStats } from "@/lib/types";

import { chosenDistricts, marketHighlights, pendingNotices } from "./market";

const eur = (v: number | null) => (v === null ? "—" : `${fmt2(v)} €`);

function rentLine(rent: RentStats) {
  if (rent.median_eur_per_m2 === null) {
    return `${fmt0(rent.contracts)} ugovora, premalo za medijan`;
  }
  return `medijan ${eur(rent.median_eur_per_m2)} po m² (${eur(rent.p25_eur_per_m2)} do ${eur(rent.p75_eur_per_m2)}, ${fmt0(rent.contracts)} ugovora)`;
}

/** Market context for this activity (ADR24). It explains the surroundings and is never scored. */
export function MarketPanel({
  profile,
  name,
  districtIds = [],
}: {
  profile: ProfileCode;
  name: string;
  districtIds?: string[];
}) {
  const market = useMarket(profile);
  if (market.isPending) return <Skeleton className="h-24" />;
  // Context must not block the results: without it the ranking stays fully usable.
  if (market.isError) return null;
  const data = market.data;
  const showCompetition = data.competitor_categories.length > 0;
  const showRent = data.districts.some((d) => d.rent.contracts > 0);
  return (
    <section className="card grid gap-3 p-4" aria-labelledby="market-title">
      <h2 id="market-title" className="flex items-center gap-2 font-medium">
        <TrendingUp aria-hidden="true" size={16} className="text-accent" /> Stanje tržišta: {name}
      </h2>
      <ul className="grid gap-1 text-sm text-muted">
        {data.lease_source_version_id ? (
          <li>
            Gradske zakupnine
            {data.lease_reference_period ? ` (${data.lease_reference_period}.)` : ""}:{" "}
            {rentLine(data.city_rent)}.
          </li>
        ) : (
          <li>Podaci o ugovorima o zakupu još nisu uvezeni.</li>
        )}
        {chosenDistricts(data, districtIds).map((line) => (
          <li key={line} className="text-text">
            {line}
          </li>
        ))}
        {marketHighlights(data).map((line) => (
          <li key={line}>{line}</li>
        ))}
        {data.pending_notices > 0 && <li>{pendingNotices(data.pending_notices)}</li>}
      </ul>
      {(showCompetition || showRent) && (
        <details className="text-sm">
          <summary className="min-h-touch cursor-pointer content-center text-accent">
            Po četvrtima
          </summary>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-left">
              <thead className="text-xs text-subtle">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Četvrt
                  </th>
                  {showCompetition && (
                    <th scope="col" className="py-1 pr-3 text-right font-medium">
                      Slični objekti
                    </th>
                  )}
                  {showCompetition && (
                    <th scope="col" className="py-1 pr-3 text-right font-medium">
                      Po km²
                    </th>
                  )}
                  <th scope="col" className="py-1 pr-3 text-right font-medium">
                    Ugovori
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    Medijan €/m²
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.districts.map((d) => (
                  <tr key={d.district_id} className="border-t border-border">
                    <th scope="row" className="py-1 pr-3 font-normal">
                      {d.name}
                    </th>
                    {showCompetition && (
                      <td className="py-1 pr-3 text-right tabular-nums">
                        {d.competitors === null ? "—" : fmt0(d.competitors)}
                      </td>
                    )}
                    {showCompetition && (
                      <td className="py-1 pr-3 text-right tabular-nums">
                        {d.competitors_per_km2 === null ? "—" : fmt2(d.competitors_per_km2)}
                      </td>
                    )}
                    <td className="py-1 pr-3 text-right tabular-nums">{fmt0(d.rent.contracts)}</td>
                    <td className="py-1 text-right tabular-nums">
                      {d.rent.median_eur_per_m2 === null ? "—" : fmt2(d.rent.median_eur_per_m2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <p className="text-xs text-subtle">
        Samo za orijentaciju, ne ulazi u bodove. {data.warnings.join(" ")}
      </p>
    </section>
  );
}
