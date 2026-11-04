import { Info } from "lucide-react";

export function TruthBanner() {
  return (
    <div className="border-b border-border bg-surface">
      <p className="page-gutter mx-auto flex max-w-6xl items-start gap-2 py-2 text-sm text-muted sm:items-center">
        <Info aria-hidden="true" size={16} className="mt-0.5 shrink-0 text-accent sm:mt-0" />
        <span>Popis Grada iz 2024. Zakupninu i natječaj prije odluke provjerite na zagreb.hr.</span>
      </p>
    </div>
  );
}
