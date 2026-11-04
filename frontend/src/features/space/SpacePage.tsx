import {
  ArrowLeft,
  CircleCheck,
  CircleHelp,
  CircleX,
  ExternalLink,
  MapPin,
  MapPinOff,
} from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { Checklist } from "@/components/Checklist";
import { StatusChip } from "@/components/StatusChip";
import { Segmented } from "@/components/ui/Segmented";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { ContributionBar } from "@/features/results/ContributionBar";
import { orderedCriteria, strengths } from "@/features/results/model";
import {
  COMPETITOR_LABEL,
  CONDITION_LABEL,
  CRITERION_LABEL,
  fmt0,
  fmt2,
  fmtDate,
  fmtDistance,
  fmtScore,
  metricValue,
  PRECISION_LABEL,
  prettyAddress,
  reasonText,
  TOPIC_LABEL,
  TRI_LABEL,
} from "@/lib/labels";
import { pendingNotices } from "@/features/results/market";
import {
  useCompetitors,
  useContextCards,
  useDistrictLayer,
  useProfiles,
  useRanking,
  useSpaceDetail,
} from "@/lib/queries";
import {
  CRITERIA,
  type CompetitorCategory,
  type Criterion,
  type Metric,
  type ProfileCode,
  type Radius,
  type RankingItem,
  type SpaceDetail,
  type Tri,
} from "@/lib/types";

const SpaceMap = lazy(() => import("@/features/map/SpaceMap"));

const PROFILES: readonly ProfileCode[] = [
  "cafe",
  "office",
  "retail",
  "food_takeaway",
  "personal_care",
  "education",
  "workshop",
];

export function SpacePage() {
  const { spaceId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const rawProfile = params.get("djelatnost");
  const profile: ProfileCode = PROFILES.includes(rawProfile as ProfileCode)
    ? (rawProfile as ProfileCode)
    : "cafe";
  const radius: Radius = params.get("radijus") === "1000" ? 1000 : 500;
  const runId = params.get("izracun");
  const detail = useSpaceDetail(spaceId, profile, radius);

  useEffect(() => {
    if (detail.data) document.title = `ProstorIQ · ${prettyAddress(detail.data.space.address)}`;
  }, [detail.data]);

  const setRadius = (r: Radius) => {
    const next = new URLSearchParams(params);
    next.set("radijus", String(r));
    setParams(next, { replace: true });
  };

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 py-6">
      <Link
        to={runId ? `/rezultati/${runId}` : `/?djelatnost=${profile}`}
        className="inline-flex min-h-touch w-fit items-center gap-1 text-sm text-muted hover:text-text"
      >
        <ArrowLeft aria-hidden="true" size={16} />{" "}
        {runId ? "Natrag na rezultate" : "Natrag na Vodič"}
      </Link>
      {detail.isError ? (
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      ) : !detail.data ? (
        <div className="grid gap-4" aria-busy="true">
          <Skeleton className="h-28" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <Detail
          detail={detail.data}
          profile={profile}
          runId={runId}
          radius={radius}
          onRadius={setRadius}
        />
      )}
    </div>
  );
}

function Detail({
  detail,
  profile,
  runId,
  radius,
  onRadius,
}: {
  detail: SpaceDetail;
  profile: ProfileCode;
  runId: string | null;
  radius: Radius;
  onRadius: (r: Radius) => void;
}) {
  const space = detail.space;
  const profiles = useProfiles();
  const profileName = profiles.data?.find((p) => p.profile === profile)?.name ?? profile;
  const ranking = useRanking(runId ?? "");
  const run = runId ? ranking.data : undefined;
  const item = run?.items.find((i) => i.space_id === space.space_id);
  const districts = useDistrictLayer();
  const geometry = space.coordinate.geometry;
  const districtPoint = districts.data?.features.find(
    (f) => f.properties.district_id === space.district_id,
  )?.properties.label_point;
  const point = geometry?.coordinates ?? districtPoint;

  return (
    <>
      <header className="card grid gap-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-1">
            <p className="eyebrow">Prostor · {profileName}</p>
            <h1 className="font-display text-2xl font-semibold sm:text-3xl">
              {prettyAddress(space.address)}
            </h1>
            <p className="flex flex-wrap gap-x-3 text-sm text-muted">
              <span>{space.district_name ?? "Četvrt nepoznata"}</span>
              <span>
                {space.area.value !== null ? `${fmt2(space.area.value)} m²` : "Površina nepoznata"}
              </span>
              <span>
                {space.position_code === "street"
                  ? "Ulični položaj"
                  : space.position_code === "other"
                    ? "Nije ulični položaj"
                    : "Položaj nepoznat"}
              </span>
            </p>
            <p className="text-xs text-subtle">
              Službeni zapis: <span className="font-mono">{space.address}</span> · ID{" "}
              <span className="font-mono">{space.space_id}</span> · popis{" "}
              {space.reference_period ?? "—"} (povijesni pregled)
            </p>
          </div>
          {item && (
            <div className="text-right">
              <p className="text-xs text-subtle">
                {item.rank !== null ? `${item.rank}. mjesto` : "Nije u poretku"}
              </p>
              <p className="font-display text-4xl font-semibold leading-none">
                {fmtScore(item.score)}
              </p>
              <p className="text-xs text-subtle">od 100</p>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={space.status.candidate_status} />
          <span className="inline-flex items-center gap-1 text-xs text-muted">
            {geometry ? (
              <MapPin aria-hidden="true" size={13} />
            ) : (
              <MapPinOff aria-hidden="true" size={13} />
            )}
            {PRECISION_LABEL[space.coordinate.precision_status]}
            {geometry ? ", ulaz nije potvrđen" : ""}
          </span>
        </div>
        {item && item.rank !== null && run && (
          <div className="grid gap-2">
            <ContributionBar
              contributions={item.contributions}
              criteria={orderedCriteria(run.criteria_used)}
            />
            <p className="text-sm text-muted">
              {strengths(item, orderedCriteria(run.criteria_used))}
            </p>
          </div>
        )}
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="grid content-start gap-5">
          <Explanation detail={detail} item={item} criteriaUsed={run?.criteria_used} />
          <Conditions detail={detail} />
          <DescriptionTags detail={detail} />
          <Surroundings
            detail={detail}
            profile={profile}
            hasCompetitors={
              (profiles.data?.find((p) => p.profile === profile)?.competitor_categories.length ??
                0) > 0
            }
            radius={radius}
            onRadius={onRadius}
          />
        </div>
        <div className="grid content-start gap-5">
          <section className="card grid gap-2 p-2" aria-label="Lokacija na karti">
            <div className="h-72 overflow-hidden rounded-lg">
              {point ? (
                <Suspense fallback={<Skeleton className="h-full w-full" />}>
                  <SpaceMap
                    cooperative
                    spaces={[
                      {
                        id: space.space_id,
                        label: prettyAddress(space.address),
                        rank: item?.rank ?? null,
                        lon: point[0],
                        lat: point[1],
                        kind: geometry
                          ? space.coordinate.precision_status === "entrance_confirmed"
                            ? "entrance"
                            : "building"
                          : "district",
                      },
                    ]}
                    selectedId={space.space_id}
                    onSelect={() => undefined}
                    radius={radius}
                    layers={["transit", "parking"]}
                  />
                </Suspense>
              ) : (
                <div className="grid h-full place-items-center p-4 text-center text-sm text-subtle">
                  Lokacija nije poznata.
                </div>
              )}
            </div>
            <p className="px-1 pb-1 text-xs text-subtle">
              {geometry
                ? `${PRECISION_LABEL[space.coordinate.precision_status]}. Krug je ${fmt0(radius)} m zračno.`
                : "Točna lokacija nepoznata, prikazana je samo četvrt. Udaljenosti se zato ne računaju."}
            </p>
          </section>
          <Notices spaceId={space.space_id} profile={profile} />
          <Checklist />
          <Sources detail={detail} />
        </div>
      </div>
    </>
  );
}

function Explanation({
  detail,
  item,
  criteriaUsed,
}: {
  detail: SpaceDetail;
  item: RankingItem | undefined;
  criteriaUsed: Criterion[] | undefined;
}) {
  return (
    <section className="card grid gap-3 p-5" aria-labelledby="why">
      <h2 id="why" className="text-lg font-semibold">
        Obrazloženje
      </h2>
      <p className="text-sm text-muted">
        {item
          ? "Vrijednost iz podataka, korisnost (0–1) i bodovi koje kriterij donosi u ovom izračunu."
          : "Vrijednosti iz podataka. Bodovi se prikazuju kad prostor otvorite iz rezultata."}
      </p>
      {/* Focusable so the table can be scrolled with the keyboard on narrow screens. */}
      <div className="overflow-x-auto rounded-md" tabIndex={0} role="region" aria-labelledby="why">
        <table className="w-full min-w-[28rem] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-subtle">
              <th scope="col" className="py-2 pr-3 font-medium">
                Kriterij
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Vrijednost
              </th>
              {item && (
                <th scope="col" className="py-2 pr-3 text-right font-medium">
                  Korisnost
                </th>
              )}
              {item && (
                <th scope="col" className="py-2 text-right font-medium">
                  Bodovi
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {CRITERIA.map((c) => {
              const metric: Metric | undefined = item?.raw_metrics[c] ?? detail.metrics[c];
              const used = criteriaUsed?.includes(c) ?? false;
              return (
                <tr key={c} className="border-b border-border/60 last:border-0">
                  <th scope="row" className="py-2 pr-3 text-left font-normal">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="h-2.5 w-2.5 rounded-sm"
                        style={{ background: `var(--crit-${c})` }}
                      />
                      {CRITERION_LABEL[c]}
                    </span>
                  </th>
                  <td className="py-2 pr-3">
                    {metric?.value != null ? (
                      metricValue(c, metric)
                    ) : (
                      <span className="text-muted">
                        Nepoznato · {reasonText(metric?.reason ?? "data_not_available")}
                      </span>
                    )}
                  </td>
                  {item && (
                    <td className="py-2 pr-3 text-right">
                      {used && item.utilities[c] !== undefined ? fmt2(item.utilities[c]) : "—"}
                    </td>
                  )}
                  {item && (
                    <td className="py-2 text-right">
                      {used && item.contributions[c] !== undefined ? (
                        fmt2(item.contributions[c])
                      ) : (
                        <span className="text-subtle">ne boduje se</span>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-subtle">Udaljenosti su zračne, nisu vrijeme hoda.</p>
    </section>
  );
}

const TRI_ICON: Record<Tri, { icon: typeof CircleCheck; tone: string }> = {
  yes: { icon: CircleCheck, tone: "text-ok" },
  no: { icon: CircleX, tone: "text-danger" },
  unknown: { icon: CircleHelp, tone: "text-warn" },
};

function Conditions({ detail }: { detail: SpaceDetail }) {
  const s = detail.space.status;
  const keys = Object.keys(CONDITION_LABEL) as (keyof typeof CONDITION_LABEL)[];
  return (
    <section className="card grid gap-3 p-5" aria-labelledby="conditions">
      <h2 id="conditions" className="text-lg font-semibold">
        Četiri obvezna uvjeta
      </h2>
      <ul className="grid gap-2">
        {keys.map((k) => {
          const v = s[k];
          const { icon: Icon, tone } = TRI_ICON[v];
          return (
            <li key={k} className="flex items-center justify-between gap-3 text-sm">
              <span>{CONDITION_LABEL[k]}</span>
              <span className={`inline-flex items-center gap-1 ${tone}`}>
                <Icon aria-hidden="true" size={15} /> {TRI_LABEL[v]}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-subtle">
        {s.checked_at
          ? `Zadnja provjera ${fmtDate(s.checked_at)}. `
          : "Nijedan uvjet još nije provjeren. "}
        Potvrda vrijedi 7 dana. Popis iz 2024. nije potvrda aktivnog natječaja.
      </p>
      <TenderRent metric={detail.metrics.cost} />
    </section>
  );
}

function DescriptionTags({ detail }: { detail: SpaceDetail }) {
  const tags = detail.description_tags;
  const pending = detail.description_tags_pending;
  const latest = tags.reduce<string | null>(
    (acc, t) => (acc === null || t.reviewed_at > acc ? t.reviewed_at : acc),
    null,
  );
  return (
    <section className="card grid gap-3 p-5" aria-labelledby="description-tags">
      <h2 id="description-tags" className="text-lg font-semibold">
        Iz opisa prostora
      </h2>
      {tags.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {tags.map((t) => (
            <li key={t.tag} className="rounded-full border border-border px-3 py-1 text-sm">
              {t.label}
              {t.value !== null && `: ${fmt0(t.value)}`}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">Nema potvrđenih oznaka.</p>
      )}
      <p className="text-xs text-subtle">
        Oznake se izvlače pravilima iz polja „Opis strukture” u službenom popisu (D01), a prikazuju
        se tek kad ih potvrdi član tima
        {latest && ` (zadnja potvrda ${fmtDate(latest)})`}. Pregled je napravljen uz pomoć AI-ja
        (Claude), koji je svaku oznaku usporedio sa službenim tekstom, a odluku je potvrdio član
        tima. Ne ulaze u bodove.
        {pending > 0 && ` Oznake koje još čekaju potvrdu (nisu prikazane): ${fmt0(pending)}.`}
      </p>
    </section>
  );
}

function isCityLink(url: string | undefined): url is string {
  if (!url) return false;
  try {
    const u = new URL(url);
    return (
      u.protocol === "https:" && (u.hostname === "zagreb.hr" || u.hostname === "www.zagreb.hr")
    );
  } catch {
    return false;
  }
}

function TenderRent({ metric }: { metric: Metric }) {
  if (metric.value === null) {
    return (
      <p className="text-sm text-muted">
        Zakupnina: nepoznata. {reasonText(metric.reason ?? "cost_not_configured")}.
      </p>
    );
  }
  const d = metric.detail;
  return (
    <div className="grid gap-1 rounded-md border border-border p-3 text-sm">
      <p>
        Početna zakupnina iz natječaja:{" "}
        <strong className="font-semibold">{metricValue("cost", metric)}</strong>
      </p>
      {d.note && <p className="text-xs text-muted">Izvor: {d.note}</p>}
      <p className="text-xs text-subtle">
        Iznos iz natječaja nije konačan ukupni trošak i ne ulazi u bodove.
        {d.checked_at && ` Provjereno ${fmtDate(d.checked_at)}.`}
      </p>
      {isCityLink(d.tender_url) && (
        <a
          href={d.tender_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-touch w-fit items-center gap-1 text-accent hover:underline"
        >
          Natječaj na zagreb.hr <ExternalLink aria-hidden="true" size={13} />
          <span className="sr-only">(otvara se u novoj kartici)</span>
        </a>
      )}
    </div>
  );
}

function Surroundings({
  detail,
  profile,
  hasCompetitors,
  radius,
  onRadius,
}: {
  detail: SpaceDetail;
  profile: ProfileCode;
  hasCompetitors: boolean;
  radius: Radius;
  onRadius: (r: Radius) => void;
}) {
  const m = detail.metrics;
  const nearest = (c: "transit" | "parking", what: string) => {
    const d = m[c].detail;
    if (m[c].value === null) return <span className="text-muted">{reasonText(m[c].reason)}</span>;
    const mode = d.mode === "tram" ? "tramvaj" : d.mode === "bus" ? "autobus" : null;
    return (
      <>
        {metricValue(c, m[c])} · {d.name ?? what}
        {mode && <span className="text-subtle"> ({mode})</span>}
      </>
    );
  };
  const counted = (c: "universities" | "culture" | "schools") => {
    const metric = m[c];
    if (metric.value === null)
      return <span className="text-muted">{reasonText(metric.reason)}</span>;
    const names = metric.detail.nearest_names ?? [];
    return (
      <>
        {fmt0(metric.value)} u 600 m
        {names.length > 0 && (
          <span className="block text-xs text-subtle">
            Najbliže: {[...new Set(names)].slice(0, 3).join(" · ")}
          </span>
        )}
      </>
    );
  };
  return (
    <section className="card grid gap-3 p-5" aria-labelledby="surroundings">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="surroundings" className="text-lg font-semibold">
          Okolina
        </h2>
        <div className="w-48">
          <Segmented<Radius>
            label="Radijus konkurencije"
            hideLabel
            size="sm"
            options={[
              { value: 500, label: "500 m" },
              { value: 1000, label: "1000 m" },
            ]}
            value={radius}
            onChange={onRadius}
          />
        </div>
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted">Javni prijevoz</dt>
        <dd>{nearest("transit", "stajalište")}</dd>
        <dt className="text-muted">Garaža</dt>
        <dd>{nearest("parking", "garaža")}</dd>
        <dt className="text-muted">Fakulteti</dt>
        <dd>{counted("universities")}</dd>
        <dt className="text-muted">Kultura</dt>
        <dd>{counted("culture")}</dd>
        <dt className="text-muted">Škole i vrtići</dt>
        <dd>{counted("schools")}</dd>
        <dt className="text-muted">
          {hasCompetitors ? "Konkurencija" : "Ugostiteljstvo i usluge"} ({fmt0(radius)} m)
        </dt>
        <dd>
          <Competitors
            spaceId={detail.space.space_id}
            bundleId={detail.dataset_bundle_id}
            profile={profile}
            radius={radius}
          />
        </dd>
      </dl>
    </section>
  );
}

const COMPETITORS_SHOWN = 8;

function Competitors({
  spaceId,
  bundleId,
  profile,
  radius,
}: {
  spaceId: string;
  bundleId: string;
  profile: ProfileCode;
  radius: Radius;
}) {
  const query = useCompetitors(spaceId, bundleId, profile, radius);
  const [all, setAll] = useState(false);
  if (query.isPending) return <Skeleton className="h-10" />;
  if (query.isError) return <span className="text-muted">Popis trenutno nije dostupan.</span>;
  const data = query.data;
  if (data.count === null) {
    return <span className="text-muted">{reasonText(data.reason ?? "data_not_available")}</span>;
  }
  const byCategory = Object.entries(data.counts_by_category)
    .map(([c, n]) => `${COMPETITOR_LABEL[c as CompetitorCategory] ?? c} ${fmt0(n ?? 0)}`)
    .join(" · ");
  const items = all ? data.items : data.items.slice(0, COMPETITORS_SHOWN);
  return (
    <div className="grid gap-2">
      <p>
        {data.count === 0 ? "Nema evidentiranih objekata" : `${fmt0(data.count)} u krugu`}
        {byCategory && <span className="text-subtle"> ({byCategory})</span>}
      </p>
      {items.length > 0 && (
        <ul className="grid gap-1 text-xs">
          {items.map((c) => (
            <li key={`${c.osm_type}/${c.osm_id}`} className="flex justify-between gap-3">
              <a
                href={`https://www.openstreetmap.org/${c.osm_type}/${c.osm_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-[28px] min-w-0 items-center truncate text-accent hover:underline"
              >
                {c.name ?? "Bez naziva"}
                <span className="sr-only"> (OpenStreetMap, otvara se u novoj kartici)</span>
              </a>
              <span className="shrink-0 text-subtle">
                {COMPETITOR_LABEL[c.category]} · {fmtDistance(c.distance_m)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {data.items.length > COMPETITORS_SHOWN && (
        <button
          type="button"
          className="min-h-touch w-fit text-xs text-accent hover:underline"
          onClick={() => setAll((v) => !v)}
          aria-expanded={all}
        >
          {all ? "Prikaži manje" : `Prikaži sve (${fmt0(data.items.length)})`}
        </button>
      )}
      <p className="text-xs text-subtle">
        Evidentirani objekti u OSM-u; popis možda nije potpun. Udaljenosti su zračne. Konkurencija
        se ne boduje.
      </p>
    </div>
  );
}

/** City notices a person approved. Failure here never hides the rest of the page (FZ06). */
function Notices({ spaceId, profile }: { spaceId: string; profile: ProfileCode }) {
  const query = useContextCards(spaceId, profile);
  if (query.isPending || query.isError) return null;
  const { items, pending_review: pending } = query.data;
  return (
    <section className="card grid gap-2 p-5" aria-labelledby="notices">
      <h2 id="notices" className="text-lg font-semibold">
        Obavijesti Grada u četvrti
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted">
          Nema potvrđenih obavijesti za ovu četvrt. To ne znači da promjena nema.
          {pending > 0 && ` ${pendingNotices(pending)}`}
        </p>
      ) : (
        <ul className="grid gap-3 text-sm">
          {items.map((card) => (
            <li key={card.card_id} className="grid gap-1">
              <span className="text-xs text-subtle">
                {TOPIC_LABEL[card.topic]}
                {card.temporal_label === "announced" && " · Najavljeno"}
                {card.temporal_label === "current" && " · Aktualno"} · {card.location.label}
              </span>
              <span>{card.summary}</span>
              <a
                href={card.source_url}
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline"
              >
                Izvorna obavijest ({card.publisher})
              </a>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-subtle">
        Lokalni AI predlaže temu, a član tima potvrđuje. Obavijesti ne mijenjaju bodove.
      </p>
    </section>
  );
}

function Sources({ detail }: { detail: SpaceDetail }) {
  return (
    <section className="card grid gap-2 p-5" aria-labelledby="sources">
      <h2 id="sources" className="text-lg font-semibold">
        Izvori
      </h2>
      <ul className="grid gap-1 text-sm text-muted">
        {detail.attribution.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
      <Link
        to="/izvori"
        className="inline-flex min-h-touch items-center text-sm text-accent hover:underline"
      >
        Svi izvori, datumi i licence
      </Link>
    </section>
  );
}
