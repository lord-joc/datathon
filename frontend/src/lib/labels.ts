/** User-facing Croatian texts for API codes, and number/address formatting. */
import type { CandidateStatus, Criterion, Metric, Precision, Tri } from "./types";

export const CRITERION_LABEL: Record<Criterion, string> = {
  transit: "Javni prijevoz",
  universities: "Fakulteti",
  culture: "Kultura",
  parking: "Garaža",
  schools: "Škole i vrtići",
  area: "Površina",
  street: "Ulica",
  competition: "Konkurencija",
  cost: "Trošak",
};

/** One line under each priority: how the criterion is scored (master prompt §5.2). */
export const CRITERION_FORMULA: Record<Criterion, string> = {
  transit: "Najbliže stajalište tramvaja ili autobusa. Puni bodovi uz stajalište, nula od 800 m.",
  universities: "Fakulteti u 600 m. Pet ili više daje pune bodove.",
  culture: "Kulturne lokacije u 600 m. Deset ili više daje pune bodove.",
  parking: "Najbliža javna garaža. Puni bodovi uz garažu, nula od 1200 m.",
  schools: "Škole i vrtići u 600 m. Šest ili više daje pune bodove.",
  area: "Što je površina bliža ciljnoj, to više bodova.",
  street: "Ulični položaj daje pune bodove, ostali položaji 40 %.",
  competition: "Manje sličnih objekata u radijusu daje više bodova.",
  cost: "Početna zakupnina iz natječaja Grada služi za usporedbu s budžetom i ne boduje se.",
};

/** Short phrase for the "Prednosti" sentence. */
export const CRITERION_STRENGTH: Record<Criterion, string> = {
  transit: "blizu javnog prijevoza",
  universities: "fakulteti u blizini",
  culture: "kulturne lokacije u blizini",
  parking: "garaža u blizini",
  schools: "škole i vrtići u blizini",
  area: "površina blizu ciljne",
  street: "ulični položaj",
  competition: "malo konkurencije",
  cost: "povoljan trošak",
};

/** Same values as --crit-* in tokens.css, for the map (MapLibre paint needs literal colours). */
export const CRITERION_COLOR: Record<Criterion, string> = {
  transit: "#3987e5",
  universities: "#d95926",
  culture: "#199e70",
  parking: "#c98500",
  schools: "#d55181",
  area: "#008300",
  street: "#9085e9",
  competition: "#e66767",
  cost: "#6b7584",
};

export const IMPORTANCE_LABEL = ["Nevažno", "Malo važno", "Važno", "Vrlo važno"] as const;

const REASON: Record<string, string> = {
  missing_coordinate: "Lokacija prostora nije poznata",
  data_not_available: "Podatak ne postoji u izvoru",
  source_unavailable: "Izvor nije dostupan",
  coverage_unchecked: "Pokrivenost OSM-a još nije provjerena",
  partial_coverage: "Podatak nedostaje dijelu prostora",
  cost_not_configured: "Zakupnina iz natječaja nije upisana",
  unknown_position: "Položaj prostora nije poznat",
  no_common_criteria: "Nema kriterija poznatog svim prostorima",
  not_applicable: "Nije primjenjivo",
  removed_incomplete: "Uklonjen iz usporedbe jer mu nedostaju podaci",
  conditional_not_included: "Potrebna provjera, nije uključen u poredak",
  vacancy_not_confirmed: "Praznost nije potvrđena",
  tender_not_confirmed: "Natječaj nije potvrđen",
  activity_not_confirmed: "Dopuštenost djelatnosti nije potvrđena",
  technical_not_confirmed: "Tehnička prikladnost nije potvrđena",
  not_vacant: "Prostor nije prazan",
  no_active_tender: "Nema aktivnog natječaja",
  activity_not_allowed: "Djelatnost nije dopuštena",
  technically_unsuitable: "Prostor nije tehnički prikladan",
  status_review_due: "Potvrda je starija od 7 dana",
  unfit_inventory: "Neuvjetan prostor (popis D02)",
};

export function reasonText(code: string | null | undefined): string {
  if (!code) return "";
  return REASON[code] ?? "Podatak nije dostupan";
}

export const STATUS_LABEL: Record<CandidateStatus, string> = {
  ready: "Spremno",
  conditional: "Potrebna provjera",
  excluded: "Isključeno",
};

export const CONDITION_LABEL = {
  physical_vacancy: "Prostor je prazan",
  tender_active: "Natječaj je aktivan",
  activity_allowed: "Djelatnost je dopuštena",
  technical_suitable: "Tehnički je prikladan",
} as const;

export const TRI_LABEL: Record<Tri, string> = { yes: "Da", no: "Ne", unknown: "Nepoznato" };

export const PRECISION_LABEL: Record<Precision, string> = {
  entrance_confirmed: "Potvrđen ulaz",
  building_approximate: "Približna lokacija zgrade",
  needs_review: "Lokacija čeka provjeru",
  missing: "Lokacija nepoznata",
};

const nf = (digits: number) =>
  new Intl.NumberFormat("hr-HR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const N0 = nf(0);
const N1 = nf(1);
const N2 = nf(2);

export const fmt0 = (n: number) => N0.format(n);
export const fmt1 = (n: number) => N1.format(n);
export const fmt2 = (n: number) => N2.format(n);
export const fmtScore = (n: number | null) => (n === null ? "—" : N2.format(n));

export function fmtDistance(m: number): string {
  return m >= 1000 ? `${N1.format(m / 1000)} km` : `${N0.format(Math.round(m))} m`;
}

/** Raw metric value with unit, or the reason why it is unknown. Unknown is never zero. */
export function metricValue(criterion: Criterion, metric: Metric | undefined): string {
  if (!metric || metric.value === null) return "Nepoznato";
  const v = metric.value;
  switch (criterion) {
    case "transit":
    case "parking":
      return `${fmtDistance(v)} zračno`;
    case "area":
      return `${fmt1(v)} m²`;
    case "street":
      return v === 1 ? "Ulični položaj" : "Nije ulični";
    case "competition":
      return metric.unit === "objects_per_km2" ? `${fmt1(v)} objekata/km²` : fmt0(v);
    case "cost":
      return `${fmt0(v)} €/mj.`;
    default:
      return fmt0(v);
  }
}

const DATE = new Intl.DateTimeFormat("hr-HR", {
  day: "numeric",
  month: "numeric",
  year: "numeric",
  timeZone: "Europe/Zagreb",
});

export function fmtDate(iso: string | null | undefined): string {
  return iso ? DATE.format(new Date(iso)) : "—";
}

const LOWER = new Set(["i", "u", "na", "od", "do", "s", "sa", "za", "pod", "nad", "kod"]);

/**
 * "TRG BANA J. JELAČIĆA 0005" -> "Trg bana J. Jelačića 5". The official record is shown
 * unchanged in the detail; this is only for reading.
 */
export function prettyAddress(raw: string): string {
  const m = /^(.*?)\s+(\d{1,4})(?:\/?\s*([A-Za-zČĆŽŠĐčćžšđ]+))?\s*$/.exec(raw.trim());
  const street = m?.[1] ?? raw;
  const number = m?.[2] ? String(Number(m[2])) : "";
  const suffix = m?.[3] ?? "";
  const words = street
    .toLocaleLowerCase("hr")
    .split(/\s+/)
    .map((w, i) =>
      i > 0 && LOWER.has(w) ? w : w.replace(/^\p{L}/u, (c) => c.toLocaleUpperCase("hr")),
    )
    .join(" ")
    .replace(
      /(\p{L})\.(\p{L})/gu,
      (_, a: string, b: string) => `${a}.${b.toLocaleUpperCase("hr")}`,
    );
  if (number === "0" || suffix.toLowerCase() === "bb") return `${words} bb`;
  return [words, number + (suffix ? suffix.toLowerCase() : "")].filter(Boolean).join(" ");
}

/** "1 prostor", "21 prostor", otherwise "prostora" (2–4 and 5+ share the genitive here). */
export function spacesWord(n: number): string {
  return n % 10 === 1 && n % 100 !== 11 ? "prostor" : "prostora";
}
