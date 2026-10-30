import { Check, LoaderCircle, MapPinOff } from "lucide-react";

import { Segmented } from "@/components/ui/Segmented";
import { Skeleton } from "@/components/ui/States";
import { errorMessage } from "@/lib/api";
import { fmt0, spacesWord } from "@/lib/labels";
import { useDistricts, useSpaceCount } from "@/lib/queries";
import type { Radius } from "@/lib/types";

import { useActiveProfile, useDebounced, useSpaceFilter } from "./hooks";
import { useGuideStore } from "./store";

const AREA_MIN = 10;
const AREA_MAX = 400;

export function SpaceStep() {
  const profile = useActiveProfile();
  const s = useGuideStore();
  const target = s.targetArea ?? profile?.target_area_m2 ?? 60;
  const districts = useDistricts();
  const filter = useDebounced(useSpaceFilter(), 200);
  const count = useSpaceCount(filter);

  const toggleRange = (on: boolean) =>
    s.set({
      limitRange: on,
      areaMin: on ? (s.areaMin ?? Math.round(target * 0.5)) : s.areaMin,
      areaMax: on ? (s.areaMax ?? Math.round(target * 2)) : s.areaMax,
    });

  return (
    <div className="grid gap-8">
      <header className="grid gap-2">
        <p className="eyebrow">Korak 2</p>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">Kakav prostor tražite?</h1>
        <p className="max-w-prose text-muted">
          Ciljna površina utječe na bodove. Raspon i četvrti samo sužavaju popis.
        </p>
      </header>

      <section className="grid gap-3" aria-labelledby="area-label">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <label id="area-label" htmlFor="target-area" className="text-sm font-medium">
            Ciljna površina
          </label>
          <span className="font-display text-xl font-semibold text-accent">{fmt0(target)} m²</span>
        </div>
        <input
          id="target-area"
          type="range"
          min={AREA_MIN}
          max={AREA_MAX}
          step={5}
          value={Math.min(AREA_MAX, Math.max(AREA_MIN, target))}
          onChange={(e) => s.set({ targetArea: Number(e.target.value) })}
          aria-valuetext={`${fmt0(target)} kvadratnih metara`}
          className="range"
        />
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-subtle">
          <span>Preporuka za ovu djelatnost: {fmt0(profile?.target_area_m2 ?? target)} m²</span>
          {s.targetArea !== null && (
            <button
              type="button"
              className="min-h-touch text-accent hover:underline"
              onClick={() => s.set({ targetArea: null })}
            >
              Vrati preporučeno
            </button>
          )}
        </div>

        <label className="flex min-h-touch cursor-pointer items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={s.limitRange}
            onChange={(e) => toggleRange(e.target.checked)}
            className="h-5 w-5 accent-[rgb(var(--accent))]"
          />
          Ograniči raspon površine
        </label>
        {s.limitRange && (
          <div className="grid grid-cols-2 gap-3 sm:max-w-sm">
            <NumberField
              label="Od (m²)"
              value={s.areaMin}
              onChange={(v) => s.set({ areaMin: v })}
            />
            <NumberField
              label="Do (m²)"
              value={s.areaMax}
              onChange={(v) => s.set({ areaMax: v })}
            />
          </div>
        )}
      </section>

      <section className="grid gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-medium">Četvrti</h2>
          <button
            type="button"
            onClick={() => s.set({ districtIds: [] })}
            className={`min-h-touch text-xs ${s.districtIds.length ? "text-accent hover:underline" : "text-subtle"}`}
            disabled={!s.districtIds.length}
          >
            {s.districtIds.length ? "Sve četvrti" : "Odabrane su sve četvrti"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2" aria-busy={districts.isPending}>
          {districts.isPending
            ? Array.from({ length: 17 }, (_, i) => <Skeleton key={i} className="h-11 w-28" />)
            : districts.data?.items.map((d) => {
                const on = s.districtIds.includes(d.district_id);
                return (
                  <button
                    key={d.district_id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => s.toggleDistrict(d.district_id)}
                    className={[
                      "inline-flex min-h-touch items-center gap-1.5 rounded-full border px-3 text-sm transition-colors",
                      on
                        ? "border-accent bg-accent/15 text-accent"
                        : "border-border text-muted hover:bg-surface-2 hover:text-text",
                    ].join(" ")}
                  >
                    {on && <Check aria-hidden="true" size={14} />}
                    {d.name}
                  </button>
                );
              })}
        </div>
      </section>

      <section className="grid gap-2 sm:max-w-sm">
        <label htmlFor="budget" className="text-sm font-medium">
          Mjesečni budžet za najam <span className="font-normal text-subtle">(neobavezno)</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            id="budget"
            type="number"
            inputMode="numeric"
            min={0}
            max={1000000}
            step={50}
            placeholder="npr. 1200"
            value={s.budget ?? ""}
            onChange={(e) =>
              s.set({ budget: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) })
            }
            aria-describedby="budget-hint"
            className="min-h-touch w-40 rounded-lg border border-border bg-bg px-3 text-text"
          />
          <span className="text-sm text-muted">€ mjesečno</span>
        </div>
        <p id="budget-hint" className="text-xs text-subtle">
          Usporedit ćemo ga samo sa stvarnom cijenom iz natječaja. Gdje cijena nije poznata, piše
          „Cijena nepoznata”, a ne procjena.
        </p>
      </section>

      <section className="sm:max-w-sm">
        <Segmented<Radius>
          label="Radijus okoline"
          options={[
            { value: 500, label: "500 m" },
            { value: 1000, label: "1000 m" },
          ]}
          value={s.radius}
          onChange={(radius) => s.set({ radius })}
        />
        <p className="mt-2 text-xs text-subtle">
          Za konkurenciju. Fakulteti, kultura i škole uvijek se broje u 600 m.
        </p>
      </section>

      <div
        className="card flex flex-wrap items-center gap-x-4 gap-y-1 bg-surface-2 p-4"
        aria-live="polite"
        aria-atomic="true"
      >
        {count.isError ? (
          <span className="text-sm text-danger">{errorMessage(count.error)}</span>
        ) : count.data ? (
          <>
            <span className="flex items-center gap-2 font-medium">
              {count.isFetching && (
                <LoaderCircle aria-hidden="true" size={16} className="animate-spin text-subtle" />
              )}
              Odgovara{" "}
              <span className="font-display text-xl text-accent">{fmt0(count.data.total)}</span>{" "}
              {spacesWord(count.data.total)}
            </span>
            {count.data.without_usable_coordinate > 0 && (
              <span className="flex items-center gap-1.5 text-xs text-subtle">
                <MapPinOff aria-hidden="true" size={14} />
                {fmt0(count.data.without_usable_coordinate)} bez poznate lokacije
              </span>
            )}
            {count.data.warnings.slice(1).map((w) => (
              <span key={w} className="w-full text-xs text-warn">
                {w}
              </span>
            ))}
          </>
        ) : (
          <span className="text-sm text-subtle">Brojim prostore…</span>
        )}
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="grid gap-1 text-xs text-muted">
      {label}
      <input
        type="number"
        inputMode="numeric"
        min={0}
        max={100000}
        value={value ?? ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? null : Math.max(0, Number(e.target.value)))
        }
        className="min-h-touch rounded-lg border border-border bg-bg px-3 text-text"
      />
    </label>
  );
}
