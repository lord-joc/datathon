import { Info } from "lucide-react";

import { PROFILES } from "./profiles";
import { useGuideStore } from "./store";

export function ProfileStep() {
  const profile = useGuideStore((s) => s.profile);
  const setProfile = useGuideStore((s) => s.setProfile);

  return (
    <fieldset className="grid gap-5">
      <legend className="mb-5 grid gap-2">
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">Što planirate otvoriti?</h1>
        <p className="max-w-prose text-muted">
          Pomoći ćemo vam suziti izbor gradskih poslovnih prostora u Zagrebu i objasniti zašto je
          neki prostor bolje rangiran.
        </p>
      </legend>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {PROFILES.map((p) => {
          const selected = profile === p.code;
          const Icon = p.icon;
          return (
            <label
              key={p.code}
              className={[
                "card flex min-h-touch cursor-pointer gap-3 p-4 transition-colors",
                selected ? "border-accent bg-accent/10" : "hover:border-subtle hover:bg-surface-2",
              ].join(" ")}
            >
              <input
                type="radio"
                name="profile"
                value={p.code}
                checked={selected}
                onChange={() => setProfile(p.code)}
                className="sr-only"
              />
              <Icon
                aria-hidden="true"
                size={22}
                className={selected ? "text-accent" : "text-muted"}
              />
              <span className="grid gap-1">
                <span className="font-medium">{p.name}</span>
                <span className="text-sm text-muted">{p.hint}</span>
                <span className="text-xs text-subtle">Ciljna površina {p.targetAreaM2} m²</span>
              </span>
            </label>
          );
        })}
      </div>

      <p className="flex items-start gap-2 text-sm text-subtle">
        <Info aria-hidden="true" size={16} className="mt-0.5 shrink-0" />
        Ostale djelatnosti još nisu podržane jer nemaju provjerena pravila bodovanja. Polje „Nešto
        drugo?” dolazi s AI prijedlogom profila.
      </p>
    </fieldset>
  );
}
