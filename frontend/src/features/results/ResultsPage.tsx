import {
  ArrowLeft,
  Columns3,
  Info,
  Layers,
  List,
  Map as MapIcon,
  TriangleAlert,
} from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { Button } from "@/components/ui/Button";
import { Segmented } from "@/components/ui/Segmented";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/States";
import { toSearch, useGuideStore } from "@/features/guide/store";
import { ApiError } from "@/lib/api";
import { CRITERION_LABEL, fmt0, fmtDate, reasonText } from "@/lib/labels";
import { useDistrictLayer, useProfiles, useRanking } from "@/lib/queries";
import type { PointLayerName, RankingItem, RankingResponse } from "@/lib/types";

import { ContributionLegend } from "./ContributionBar";
import { budgetFit, groupItems, mapSpaces, orderedCriteria, useSpaceIndex } from "./model";
import { ResultCard } from "./ResultCard";

const SpaceMap = lazy(() => import("@/features/map/SpaceMap"));

const LAYER_OPTIONS: { value: PointLayerName; label: string }[] = [
  { value: "transit", label: "Stajališta" },
  { value: "parking", label: "Garaže" },
  { value: "universities", label: "Fakulteti" },
  { value: "culture", label: "Kultura" },
  { value: "schools", label: "Škole i vrtići" },
];

export function ResultsPage() {
  const { runId = "" } = useParams();
  const ranking = useRanking(runId);

  useEffect(() => {
    document.title = "ProstorIQ · Rezultati";
  }, []);

  if (ranking.isPending) {
    return (
      <div className="mx-auto grid max-w-6xl gap-4 py-8" aria-busy="true">
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (ranking.isError) return <RunUnavailable error={ranking.error} />;
  return <Results run={ranking.data} />;
}

function RunUnavailable({ error }: { error: unknown }) {
  const code = error instanceof ApiError ? error.problem.status : 0;
  const text =
    code === 403 || code === 422
      ? "Spremljeni izračun može se otvoriti samo u kartici preglednika u kojoj je napravljen."
      : code === 410
        ? "Ovaj izračun je istekao."
        : code === 404
          ? "Izračun ne postoji."
          : null;
  return (
    <div className="mx-auto grid max-w-3xl gap-4 py-10">
      {text ? (
        <EmptyState title={text}>
          <p>Napravite novi izračun u Vodiču. Postavke iz poveznice se zadržavaju.</p>
          <Link
            to="/"
            className="mt-3 inline-flex min-h-touch items-center text-accent hover:underline"
          >
            Otvori Vodič
          </Link>
        </EmptyState>
      ) : (
        <ErrorState error={error} />
      )}
    </div>
  );
}

function Results({ run }: { run: RankingResponse }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const budgetRaw = Number(params.get("budzet"));
  const budget =
    params.has("budzet") && Number.isFinite(budgetRaw) && budgetRaw >= 0 ? budgetRaw : null;
  const [onlyWithin, setOnlyWithin] = useState(false);
  const guide = useGuideStore();
  const profiles = useProfiles();
  const profile = profiles.data?.find((p) => p.profile === run.profile);
  const index = useSpaceIndex(run.profile);
  const districts = useDistrictLayer();
  const [selected, setSelected] = useState<string | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [view, setView] = useState<"list" | "map">("list");
  const [layers, setLayers] = useState<PointLayerName[]>([]);
  const cards = useRef(new Map<string, HTMLLIElement>());

  const criteria = orderedCriteria(run.criteria_used);
  const priced =
    budget === null ? 0 : run.items.filter((i) => budgetFit(i, budget) !== "unknown").length;
  const within =
    budget === null ? 0 : run.items.filter((i) => budgetFit(i, budget) === "within").length;
  const visible = useMemo(
    () =>
      budget !== null && onlyWithin
        ? run.items.filter((i) => budgetFit(i, budget) === "within")
        : run.items,
    [run.items, budget, onlyWithin],
  );
  const groups = useMemo(() => groupItems(visible), [visible]);
  const ranked = groups.ready.length + groups.conditional.length;
  const placed = useMemo(
    () =>
      mapSpaces(
        visible.filter((i) => i.rank !== null),
        index.data,
        districts.data,
      ),
    [visible, index.data, districts.data],
  );
  const radius = run.radius_m;

  const settingsHref =
    guide.profile === run.profile
      ? `/?${toSearch(guide, 2)}`
      : `/?djelatnost=${run.profile}&korak=3`;
  const detailHref = (id: string) =>
    `/prostor/${id}?djelatnost=${run.profile}&radijus=${run.radius_m}&izracun=${run.ranking_run_id}`;

  const selectFromMap = (id: string) => {
    setSelected(id);
    setView("list");
    cards.current.get(id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    cards.current.get(id)?.querySelector("a")?.focus({ preventScroll: true });
  };

  const card = (item: RankingItem) => (
    <ResultCard
      key={item.space_id}
      ref={(el) => {
        if (el) cards.current.set(item.space_id, el);
        else cards.current.delete(item.space_id);
      }}
      item={item}
      summary={index.data?.get(item.space_id)}
      criteria={criteria}
      detailHref={detailHref(item.space_id)}
      selected={selected === item.space_id}
      compared={compare.includes(item.space_id)}
      compareDisabled={compare.length >= 3}
      onSelect={() => setSelected(item.space_id)}
      budget={budget}
      onCompare={(on) =>
        setCompare((c) =>
          on ? [...c, item.space_id].slice(0, 3) : c.filter((x) => x !== item.space_id),
        )
      }
    />
  );

  return (
    <div className="mx-auto grid w-full max-w-7xl gap-5 py-6">
      <header className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link
            to={settingsHref}
            className="inline-flex min-h-touch items-center gap-1 text-sm text-muted hover:text-text"
          >
            <ArrowLeft aria-hidden="true" size={16} /> Promijeni postavke
          </Link>
          {run.historical && (
            <span className="inline-flex items-center gap-1 rounded-full border border-warn/40 px-2.5 py-1 text-xs text-warn">
              <Info aria-hidden="true" size={13} /> Izračun nad starijim paketom podataka
            </span>
          )}
        </div>
        <div className="grid gap-1">
          <p className="eyebrow">Rezultati · {profile?.name ?? run.profile}</p>
          <h1 className="font-display text-2xl font-semibold sm:text-3xl" aria-live="polite">
            Rangirano {fmt0(ranked)} od {fmt0(run.items.length)} prostora
          </h1>
          <p className="text-sm text-muted">
            Upotrijebljeno {fmt0(run.coverage_default_profile)} % zadanih težina profila ·
            pokrivenost aktivnih kriterija {fmt0(run.coverage_active)} % · izračun{" "}
            {fmtDate(run.created_at)}
          </p>
        </div>

        {budget !== null && (
          <div className="card flex flex-wrap items-center justify-between gap-3 bg-surface-2 p-3 text-sm">
            <p className="text-muted">
              Budžet do <span className="font-medium text-text">{fmt0(budget)} € mjesečno</span>.{" "}
              {priced === 0
                ? "Ni za jedan prostor još nema cijene iz natječaja, pa se uklapanje ne može provjeriti."
                : `Cijena je poznata za ${fmt0(priced)} prostora, a ${fmt0(within)} je unutar budžeta.`}
            </p>
            <label className="inline-flex min-h-touch items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={onlyWithin}
                disabled={priced === 0}
                onChange={(e) => setOnlyWithin(e.target.checked)}
                className="h-4 w-4 accent-[rgb(var(--accent))]"
              />
              Samo unutar budžeta
            </label>
          </div>
        )}

        {run.excluded_criteria.length > 0 && (
          <ul className="grid gap-1 text-sm text-muted">
            {run.excluded_criteria.map((e) => (
              <li key={e.criterion} className="flex items-start gap-2">
                <TriangleAlert aria-hidden="true" size={15} className="mt-0.5 shrink-0 text-warn" />
                <span>
                  <span className="text-text">{CRITERION_LABEL[e.criterion]}</span> se ne boduje:{" "}
                  {reasonText(e.reason).toLocaleLowerCase("hr")}.
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <ContributionLegend criteria={criteria} />
          <Button
            onClick={() =>
              navigate(`/rezultati/${run.ranking_run_id}/usporedba?prostori=${compare.join(",")}`)
            }
            disabled={compare.length < 2}
          >
            <Columns3 aria-hidden="true" size={16} /> Usporedi ({compare.length}/3)
          </Button>
        </div>
        {compare.length >= 3 && (
          <p className="text-xs text-subtle" role="status">
            Usporediti se mogu najviše 3 prostora. Uklonite jedan da biste dodali drugi.
          </p>
        )}

        <div className="md:hidden">
          <Segmented<"list" | "map">
            label="Prikaz"
            hideLabel
            options={[
              { value: "list", label: "Popis" },
              { value: "map", label: "Karta" },
            ]}
            value={view}
            onChange={setView}
          />
        </div>
      </header>

      <div className="grid gap-5 md:grid-cols-[minmax(0,55fr)_minmax(0,45fr)]">
        <div className={`grid content-start gap-6 ${view === "map" ? "hidden md:grid" : ""}`}>
          {ranked === 0 && (
            <EmptyState title="Nijedan prostor nije rangiran">
              Svim prostorima nedostaju isti podaci. Vratite se na postavke i uključite više
              kriterija.
            </EmptyState>
          )}
          <Group
            title="Spremno"
            hint="Sva četiri uvjeta su potvrđena."
            items={groups.ready}
            render={card}
          />
          <Group
            title="Potrebna provjera"
            hint="Natječaj, praznost, dopuštenost djelatnosti ili tehnički uvjeti nisu potvrđeni. Prije odluke provjerite službenu objavu."
            items={groups.conditional}
            render={card}
          />
          {groups.unranked.length > 0 && (
            <details className="card p-4">
              <summary className="min-h-touch cursor-pointer content-center font-medium">
                Nisu u poretku ({fmt0(groups.unranked.length)})
              </summary>
              <ul className="mt-3 grid gap-3">{groups.unranked.map(card)}</ul>
            </details>
          )}
        </div>

        <aside
          className={`${view === "list" ? "hidden md:block" : ""} md:sticky md:top-[72px] md:self-start`}
          aria-label="Karta rezultata"
        >
          <div className="card grid gap-2 p-2">
            <div className="h-[calc(100dvh-260px)] min-h-[320px] overflow-hidden rounded-lg md:h-[calc(100dvh-200px)]">
              <Suspense fallback={<Skeleton className="h-full w-full" />}>
                <SpaceMap
                  spaces={placed.spaces}
                  selectedId={selected}
                  onSelect={selectFromMap}
                  radius={radius}
                  layers={layers}
                />
              </Suspense>
            </div>
            <fieldset className="flex flex-wrap items-center gap-2 px-1 pb-1">
              <legend className="sr-only">Slojevi karte</legend>
              <Layers aria-hidden="true" size={15} className="text-subtle" />
              {LAYER_OPTIONS.map((o) => {
                const on = layers.includes(o.value);
                return (
                  <button
                    key={o.value}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      setLayers((l) => (on ? l.filter((x) => x !== o.value) : [...l, o.value]))
                    }
                    className={`min-h-touch rounded-full border px-3 text-xs ${on ? "border-accent bg-accent/10 text-accent-strong" : "border-border text-muted hover:text-text"}`}
                  >
                    <span
                      aria-hidden="true"
                      className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-middle"
                      style={{ background: `var(--crit-${o.value})` }}
                    />
                    {o.label}
                  </button>
                );
              })}
            </fieldset>
            <p className="flex flex-wrap gap-x-3 px-1 pb-1 text-xs text-subtle">
              <span className="inline-flex items-center gap-1">
                <MapIcon aria-hidden="true" size={13} /> Točke su približne lokacije zgrada.
              </span>
              {placed.districtOnly > 0 && (
                <span>{fmt0(placed.districtOnly)} prikazano samo po četvrti (isprekidano).</span>
              )}
              {placed.hidden > 0 && <span>{fmt0(placed.hidden)} nije na karti.</span>}
              <span className="inline-flex items-center gap-1 md:hidden">
                <List aria-hidden="true" size={13} /> Svi prostori su i u popisu.
              </span>
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Group({
  title,
  hint,
  items,
  render,
}: {
  title: string;
  hint: string;
  items: RankingItem[];
  render: (item: RankingItem) => JSX.Element;
}) {
  if (items.length === 0) return null;
  return (
    <section className="grid gap-3" aria-label={title}>
      <div className="grid gap-1">
        <h2 className="text-lg font-semibold">
          {title} <span className="text-muted">({fmt0(items.length)})</span>
        </h2>
        <p className="text-sm text-subtle">{hint}</p>
      </div>
      <ol className="grid gap-3">{items.map(render)}</ol>
    </section>
  );
}
