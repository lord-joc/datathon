import { Info } from "lucide-react";

export function TruthBanner() {
  return (
    <div className="border-b border-border bg-surface">
      <p className="page-gutter mx-auto flex max-w-6xl items-start gap-2 py-2 text-xs text-muted sm:items-center">
        <Info aria-hidden="true" size={14} className="mt-0.5 shrink-0 text-accent sm:mt-0" />
        <span>
          Popis Grada iz 2024. Natječaj i zakupnina vrijede samo gdje su navedeni s poveznicom na
          zagreb.hr. Prije odluke provjerite službenu objavu.
        </span>
      </p>
    </div>
  );
}
