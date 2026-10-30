import { ChevronRight, MapPin, MapPinOff, Wallet } from "lucide-react";
import { forwardRef } from "react";
import { Link } from "react-router";

import { StatusChip } from "@/components/StatusChip";
import { fmt0, fmtScore, prettyAddress, reasonText } from "@/lib/labels";
import type { Criterion, RankingItem, SpaceSummary } from "@/lib/types";

import { ContributionBar } from "./ContributionBar";
import { budgetFit, strengths, weaknesses, type BudgetFit } from "./model";

const BUDGET_TEXT: Record<BudgetFit, string> = {
  within: "Unutar budžeta",
  over: "Iznad budžeta",
  unknown: "Cijena nepoznata",
};

interface ResultCardProps {
  item: RankingItem;
  summary: SpaceSummary | undefined;
  criteria: Criterion[];
  detailHref: string;
  selected: boolean;
  compared: boolean;
  compareDisabled: boolean;
  onSelect: () => void;
  onCompare: (on: boolean) => void;
  budget: number | null;
}

export const ResultCard = forwardRef<HTMLLIElement, ResultCardProps>(function ResultCard(
  {
    item,
    summary,
    criteria,
    detailHref,
    selected,
    compared,
    compareDisabled,
    onSelect,
    onCompare,
    budget,
  },
  ref,
) {
  const address = summary ? prettyAddress(summary.address) : `Prostor ${item.space_id}`;
  const located = item.coordinate_snapshot.geometry !== null;
  const weak = item.rank !== null ? weaknesses(item, criteria) : null;
  return (
    <li
      ref={ref}
      onMouseEnter={onSelect}
      className={[
        "card grid gap-3 p-4 transition-colors",
        selected ? "border-accent/70 bg-surface-2" : "",
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className={[
            "grid h-8 w-8 shrink-0 place-items-center rounded-full border text-sm font-semibold",
            selected ? "border-accent bg-accent text-bg" : "border-border text-muted",
          ].join(" ")}
        >
          {item.rank ?? "–"}
        </span>
        <div className="grid min-w-0 flex-1 gap-1">
          <h3 className="font-medium leading-snug">
            <Link to={detailHref} className="hover:text-accent hover:underline" onFocus={onSelect}>
              <span className="sr-only">{item.rank !== null ? `${item.rank}. mjesto: ` : ""}</span>
              {address}
            </Link>
          </h3>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            <span>{summary?.district_name ?? "Četvrt nepoznata"}</span>
            <span>
              {summary?.area.value != null
                ? `${fmt0(summary.area.value)} m²`
                : "Površina nepoznata"}
            </span>
            <span className="font-mono text-subtle">ID {item.space_id}</span>
          </p>
        </div>
        <div className="text-right">
          <span className="font-display text-2xl font-semibold leading-none text-text">
            {fmtScore(item.score)}
          </span>
          <span className="block text-xs text-subtle">od 100</span>
        </div>
      </div>

      {item.rank !== null ? (
        <>
          <ContributionBar contributions={item.contributions} criteria={criteria} />
          <p className="text-sm text-muted">
            {strengths(item, criteria)} {weak && <span className="text-subtle">{weak}</span>}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted">{reasonText(item.reason)}</p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={item.candidate_status} />
          {budget !== null && (
            <span
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${budgetFit(item, budget) === "within" ? "border-accent/50 text-accent" : "border-border text-muted"}`}
            >
              <Wallet aria-hidden="true" size={13} />
              {BUDGET_TEXT[budgetFit(item, budget)]}
            </span>
          )}
          <span className="inline-flex items-center gap-1 text-xs text-subtle">
            {located ? (
              <MapPin aria-hidden="true" size={13} />
            ) : (
              <MapPinOff aria-hidden="true" size={13} />
            )}
            {located ? "Približna lokacija zgrade" : "Lokacija nepoznata, samo četvrt"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {item.rank !== null && (
            <label className="inline-flex min-h-touch cursor-pointer items-center gap-2 px-2 text-xs text-muted">
              <input
                type="checkbox"
                checked={compared}
                disabled={compareDisabled && !compared}
                onChange={(e) => onCompare(e.target.checked)}
                className="h-4 w-4 accent-[rgb(var(--accent))]"
              />
              Usporedi
            </label>
          )}
          <Link
            to={detailHref}
            className="inline-flex min-h-touch items-center gap-1 rounded-md px-2 text-sm text-accent hover:bg-surface-2"
            aria-label={`Detalj: ${address}`}
          >
            Detalj <ChevronRight aria-hidden="true" size={16} />
          </Link>
        </div>
      </div>
    </li>
  );
});
