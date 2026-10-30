import { CRITERION_LABEL, fmt1 } from "@/lib/labels";
import type { Criterion } from "@/lib/types";

interface ContributionBarProps {
  contributions: Partial<Record<Criterion, number>>;
  criteria: Criterion[];
  className?: string;
}

/**
 * The score split by criterion: each segment is that criterion's points out of 100. Shades of
 * blue and grey only; the same criterion always has the same shade (master prompt §7.2).
 */
export function ContributionBar({ contributions, criteria, className = "" }: ContributionBarProps) {
  const parts = criteria.map((c) => ({ c, v: contributions[c] ?? 0 })).filter((p) => p.v > 0);
  const text = parts.map((p) => `${CRITERION_LABEL[p.c]} ${fmt1(p.v)}`).join(", ");
  return (
    <div className={className}>
      <div
        aria-hidden="true"
        className="flex h-2.5 w-full gap-px overflow-hidden rounded-full bg-surface-2"
      >
        {parts.map((p) => (
          <span
            key={p.c}
            title={`${CRITERION_LABEL[p.c]}: ${fmt1(p.v)} bodova`}
            className="h-full first:rounded-l-full"
            style={{ width: `${p.v}%`, background: `var(--crit-${p.c})` }}
          />
        ))}
      </div>
      <span className="sr-only">Doprinos bodovima: {text || "nema"}.</span>
    </div>
  );
}

export function ContributionLegend({ criteria }: { criteria: Criterion[] }) {
  return (
    <ul
      className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted"
      aria-label="Legenda kriterija"
    >
      {criteria.map((c) => (
        <li key={c} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="h-2.5 w-2.5 rounded-sm"
            style={{ background: `var(--crit-${c})` }}
          />
          {CRITERION_LABEL[c]}
        </li>
      ))}
    </ul>
  );
}
