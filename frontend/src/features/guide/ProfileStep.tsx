import { Info } from "lucide-react";

import { ErrorState, Skeleton } from "@/components/ui/States";
import { fmt0 } from "@/lib/labels";
import { useProfiles } from "@/lib/queries";

import { profileIcon } from "./profiles";
import { SuggestProfile } from "./SuggestProfile";
import { useGuideStore } from "./store";

export function ProfileStep() {
  const profile = useGuideStore((s) => s.profile);
  const setProfile = useGuideStore((s) => s.setProfile);
  const profiles = useProfiles();

  return (
    <fieldset className="grid gap-5">
      <legend className="mb-5 grid gap-2">
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">Što planirate otvoriti?</h1>
        <p className="max-w-prose text-muted">
          Pomoći ćemo vam suziti izbor gradskih poslovnih prostora u Zagrebu i objasniti zašto je
          neki prostor bolje rangiran.
        </p>
      </legend>

      {profiles.isError ? (
        <ErrorState error={profiles.error} onRetry={() => void profiles.refetch()} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-busy={profiles.isPending}>
          {profiles.isPending
            ? Array.from({ length: 7 }, (_, i) => <Skeleton key={i} className="h-[92px]" />)
            : profiles.data.map((p) => {
                const selected = profile === p.profile;
                const Icon = profileIcon(p.icon);
                return (
                  <label
                    key={p.profile}
                    className={[
                      "card spot flex min-h-touch cursor-pointer gap-3 p-4 transition-colors has-[:focus-visible]:shadow-[var(--focus-ring)]",
                      selected ? "border-accent bg-accent/[0.06]" : "",
                    ].join(" ")}
                  >
                    <input
                      type="radio"
                      name="profile"
                      value={p.profile}
                      checked={selected}
                      onChange={() => setProfile(p.profile)}
                      className="sr-only"
                    />
                    <Icon
                      aria-hidden="true"
                      size={22}
                      className={selected ? "text-accent" : "text-muted"}
                    />
                    <span className="grid gap-1">
                      <span className="font-medium">{p.name}</span>
                      <span className="text-sm text-muted">{p.summary}</span>
                      <span className="text-xs text-subtle">
                        Ciljna površina {fmt0(p.target_area_m2)} m²
                      </span>
                    </span>
                  </label>
                );
              })}
        </div>
      )}

      {profiles.data && <SuggestProfile profiles={profiles.data} onChoose={setProfile} />}

      <p className="flex items-start gap-2 text-sm text-subtle">
        <Info aria-hidden="true" size={16} className="mt-0.5 shrink-0" />
        Ostale djelatnosti još nisu podržane jer nemaju provjerena pravila bodovanja.
      </p>
    </fieldset>
  );
}
