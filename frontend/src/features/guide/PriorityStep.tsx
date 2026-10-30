import { Info, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Segmented } from "@/components/ui/Segmented";
import { Skeleton } from "@/components/ui/States";
import { CRITERION_FORMULA, CRITERION_LABEL, IMPORTANCE_LABEL } from "@/lib/labels";

import { useActiveProfile } from "./hooks";
import { ADJUSTABLE, levelsFromWeights, useGuideStore, type Level } from "./store";

const OPTIONS = IMPORTANCE_LABEL.map((label, value) => ({ value: value as Level, label }));

export function PriorityStep() {
  const profile = useActiveProfile();
  const levels = useGuideStore((s) => s.levels);
  const setLevel = useGuideStore((s) => s.setLevel);
  const resetLevels = useGuideStore((s) => s.resetLevels);

  if (!profile) return <Skeleton className="h-96" />;
  const shown = levels ?? levelsFromWeights(profile.weights);
  const noneActive = ADJUSTABLE.every((c) => shown[c] === 0);

  return (
    <div className="grid gap-6">
      <header className="grid gap-2">
        <p className="eyebrow">Korak 3</p>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">Što vam je važno?</h1>
        <p className="max-w-prose text-muted">
          Preporučene razine za „{profile.name}” već su postavljene. Promijenite samo ono što za vas
          vrijedi drugačije.
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-subtle" aria-live="polite">
          {levels === null
            ? "Koriste se preporučene težine profila."
            : "Koristite vlastite razine."}
        </p>
        <Button variant="ghost" onClick={resetLevels} disabled={levels === null}>
          <RotateCcw aria-hidden="true" size={16} /> Vrati preporučeno
        </Button>
      </div>

      <ul className="grid gap-3">
        {ADJUSTABLE.map((c) => (
          <li
            key={c}
            className="card grid gap-3 p-4 md:grid-cols-[1fr_minmax(0,26rem)] md:items-center"
          >
            <div className="grid gap-1">
              <span className="flex items-center gap-2 font-medium">
                <span
                  aria-hidden="true"
                  className="h-3 w-3 rounded-sm"
                  style={{ background: `var(--crit-${c})` }}
                />
                {CRITERION_LABEL[c]}
              </span>
              <span className="text-sm text-muted">{CRITERION_FORMULA[c]}</span>
            </div>
            <Segmented<Level>
              label={`Važnost: ${CRITERION_LABEL[c]}`}
              hideLabel
              size="sm"
              options={OPTIONS}
              value={shown[c]}
              onChange={(level) => setLevel(c, level, profile.weights)}
            />
          </li>
        ))}
        <li className="card grid gap-1 border-dashed p-4 opacity-80">
          <span className="font-medium">{CRITERION_LABEL.cost}</span>
          <span className="text-sm text-muted">
            {CRITERION_FORMULA.cost} Njegova težina ostaje u profilu pa pokrivenost pokazuje koliko
            odluke otvoreni podaci ne mogu pokriti.
          </span>
        </li>
      </ul>

      {noneActive && (
        <p role="alert" className="flex items-start gap-2 text-sm text-warn">
          <Info aria-hidden="true" size={16} className="mt-0.5 shrink-0" />
          Odaberite barem jedan kriterij koji je važan.
        </p>
      )}
    </div>
  );
}
