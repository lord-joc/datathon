import { ArrowLeft, Info } from "lucide-react";
import { useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { Checklist } from "@/components/Checklist";
import { StatusChip } from "@/components/StatusChip";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { ContributionBar } from "@/features/results/ContributionBar";
import { orderedCriteria, strengths, useSpaceIndex } from "@/features/results/model";
import {
  CRITERION_LABEL,
  fmt2,
  fmtScore,
  metricValue,
  PRECISION_LABEL,
  prettyAddress,
} from "@/lib/labels";
import { useRanking } from "@/lib/queries";

const MAX = 3;

/**
 * Up to three spaces from one saved run. Scores come from the snapshot unchanged (no
 * re-normalisation over the subset, master prompt §2.2).
 */
export function ComparePage() {
  const { runId = "" } = useParams();
  const [params] = useSearchParams();
  const ranking = useRanking(runId);
  const index = useSpaceIndex(ranking.data?.profile);
  const requested = (params.get("prostori") ?? "")
    .split(",")
    .filter((id) => /^[0-9]{1,12}$/.test(id));
  const ids = [...new Set(requested)].slice(0, MAX);

  useEffect(() => {
    document.title = "ProstorIQ · Usporedba";
  }, []);

  const back = (
    <Link
      to={`/rezultati/${runId}`}
      className="inline-flex min-h-touch w-fit items-center gap-1 text-sm text-muted hover:text-text"
    >
      <ArrowLeft aria-hidden="true" size={16} /> Natrag na rezultate
    </Link>
  );
  if (ranking.isPending) return <Skeleton className="mx-auto my-8 h-96 max-w-6xl" />;
  if (ranking.isError) {
    return (
      <div className="mx-auto grid max-w-3xl gap-4 py-8">
        {back}
        <ErrorState error={ranking.error} />
      </div>
    );
  }
  const run = ranking.data;
  const items = ids
    .map((id) => run.items.find((i) => i.space_id === id && i.rank !== null))
    .filter((i) => i !== undefined);
  const criteria = orderedCriteria(run.criteria_used);

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 py-6">
      {back}
      <header className="grid gap-1">
        <p className="eyebrow">Usporedba</p>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">
          {items.length} {items.length === 1 ? "prostor" : "prostora"} iz istog izračuna
        </h1>
        <p className="text-sm text-muted">
          Bodovi su isti kao u rezultatima i ne preračunavaju se za ovaj podskup.
        </p>
      </header>
      {requested.length > MAX && (
        <p role="status" className="flex items-center gap-2 text-sm text-warn">
          <Info aria-hidden="true" size={16} /> Usporediti se mogu najviše 3 prostora. Prikazana su
          prva tri.
        </p>
      )}
      {items.length < 2 ? (
        <EmptyState title="Odaberite barem dva rangirana prostora">
          U rezultatima označite „Usporedi” kod 2 ili 3 prostora.
        </EmptyState>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full min-w-[40rem] text-sm">
            <caption className="sr-only">Usporedba prostora po kriterijima</caption>
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="w-40 p-4 text-left text-xs font-medium text-subtle">
                  Prostor
                </th>
                {items.map((i) => {
                  const s = index.data?.get(i.space_id);
                  return (
                    <th
                      key={i.space_id}
                      scope="col"
                      className="p-4 text-left align-top font-normal"
                    >
                      <span className="block text-xs text-subtle">{i.rank}. mjesto</span>
                      <Link
                        to={`/prostor/${i.space_id}?djelatnost=${run.profile}&radijus=${run.radius_m}&izracun=${run.ranking_run_id}`}
                        className="font-medium hover:text-accent hover:underline"
                      >
                        {s ? prettyAddress(s.address) : `Prostor ${i.space_id}`}
                      </Link>
                      <span className="block text-xs text-muted">{s?.district_name ?? ""}</span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-border/60">
                <th scope="row" className="p-4 text-left text-xs font-medium text-subtle">
                  Rezultat
                </th>
                {items.map((i) => (
                  <td key={i.space_id} className="grid gap-2 p-4">
                    <span className="font-display text-3xl font-semibold leading-none">
                      {fmtScore(i.score)}
                    </span>
                    <ContributionBar contributions={i.contributions} criteria={criteria} />
                    <span className="text-xs text-muted">{strengths(i, criteria)}</span>
                  </td>
                ))}
              </tr>
              <tr className="border-b border-border/60">
                <th scope="row" className="p-4 text-left text-xs font-medium text-subtle">
                  Status
                </th>
                {items.map((i) => (
                  <td key={i.space_id} className="p-4">
                    <StatusChip status={i.candidate_status} />
                  </td>
                ))}
              </tr>
              {criteria.map((c) => (
                <tr key={c} className="border-b border-border/60">
                  <th scope="row" className="p-4 text-left font-normal">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="h-2.5 w-2.5 rounded-sm"
                        style={{ background: `var(--crit-${c})` }}
                      />
                      {CRITERION_LABEL[c]}
                    </span>
                  </th>
                  {items.map((i) => (
                    <td key={i.space_id} className="p-4">
                      {metricValue(c, i.raw_metrics[c])}
                      <span className="block text-xs text-subtle">
                        {fmt2(i.contributions[c] ?? 0)} bodova
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
              <tr>
                <th scope="row" className="p-4 text-left text-xs font-medium text-subtle">
                  Lokacija
                </th>
                {items.map((i) => (
                  <td key={i.space_id} className="p-4 text-xs text-muted">
                    {PRECISION_LABEL[i.coordinate_snapshot.precision_status]}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <Checklist title="Prije odluke provjerite za svaki prostor" />
    </div>
  );
}
