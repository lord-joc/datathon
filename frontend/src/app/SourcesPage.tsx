import { CircleCheck, CircleDashed, CircleSlash, ExternalLink } from "lucide-react";
import { useEffect } from "react";

import { ErrorState, Skeleton } from "@/components/ui/States";
import { fmtDate } from "@/lib/labels";
import { useSources } from "@/lib/queries";
import type { SourcePublic } from "@/lib/types";

const AVAILABILITY: Record<
  SourcePublic["availability"],
  { label: string; icon: typeof CircleCheck; tone: string }
> = {
  available: { label: "U aktivnom paketu", icon: CircleCheck, tone: "text-ok" },
  unavailable: { label: "Nije uvezen", icon: CircleDashed, tone: "text-warn" },
  disabled: { label: "Isključen", icon: CircleSlash, tone: "text-subtle" },
};

export function SourcesPage() {
  const sources = useSources();
  useEffect(() => {
    document.title = "ProstorIQ · Izvori";
  }, []);

  return (
    <div className="mx-auto grid max-w-4xl gap-6 py-8">
      <header className="grid gap-2">
        <p className="eyebrow">Izvori</p>
        <h1 className="font-display text-2xl font-semibold sm:text-3xl">
          Izvori podataka i licence
        </h1>
        <p className="max-w-prose text-muted">
          Svaki broj u aplikaciji dolazi iz jednog od ovih izvora. Prikazane su verzije iz aktivnog
          paketa podataka.
        </p>
      </header>

      {sources.isError ? (
        <ErrorState error={sources.error} onRetry={() => void sources.refetch()} />
      ) : sources.isPending ? (
        <div className="grid gap-3" aria-busy="true">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <ul className="grid gap-3">
          {sources.data.items.map((s) => {
            const a = AVAILABILITY[s.availability];
            return (
              <li key={s.source_code} className="card grid gap-2 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h2 className="font-medium">
                    <span className="mr-2 font-mono text-xs text-subtle">{s.source_code}</span>
                    {s.name}
                  </h2>
                  <span className={`inline-flex items-center gap-1 text-xs ${a.tone}`}>
                    <a.icon aria-hidden="true" size={14} /> {a.label}
                  </span>
                </div>
                <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[8rem_1fr]">
                  <dt className="text-subtle">Izdavatelj</dt>
                  <dd>{s.publisher}</dd>
                  <dt className="text-subtle">Licenca</dt>
                  <dd>{s.license_id}</dd>
                  <dt className="text-subtle">Razdoblje</dt>
                  <dd>{s.reference_period ?? "—"}</dd>
                  <dt className="text-subtle">Preuzeto</dt>
                  <dd>
                    {fmtDate(s.fetched_at)}
                    {s.last_checked_at && (
                      <span className="text-subtle">
                        {" "}
                        · provjereno {fmtDate(s.last_checked_at)}
                      </span>
                    )}
                  </dd>
                  <dt className="text-subtle">Atribucija</dt>
                  <dd className="text-muted">{s.attribution}</dd>
                </dl>
                {s.limitations.length > 0 && (
                  <ul className="grid gap-1 text-xs text-warn">
                    {s.limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                )}
                {s.catalog_url?.startsWith("https://") && (
                  <a
                    href={s.catalog_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-touch w-fit items-center gap-1 text-sm text-accent hover:underline"
                  >
                    Skup podataka u katalogu <ExternalLink aria-hidden="true" size={13} />
                    <span className="sr-only">(otvara se u novoj kartici)</span>
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <section className="card grid gap-2 p-5 text-sm text-muted">
        <h2 className="text-base font-semibold text-text">AI u aplikaciji</h2>
        <p>
          Prijedlog djelatnosti iz slobodnog opisa radi lokalni model
          paraphrase-multilingual-MiniLM-L12-v2 (Apache-2.0), na našem poslužitelju i bez slanja
          podataka trećima. Opis se ne sprema. Model predlaže, a vi birate. Kalibriran je na malom
          skupu primjera, pa može pogriješiti.
        </p>
        <p>
          Oznake iz službenog „Opisa strukture” (npr. podrum, ulična zgrada, broj prostorija)
          izvlače pravila, a prikazuju se tek kad ih potvrdi član tima. Pregled 531 oznake (31. 10.
          2026.) napravljen je uz pomoć AI-ja (Claude) prema službenom tekstu, a potvrdio ga je član
          tima; 13 oznaka je odbijeno. Ni prijedlog ni oznake ne mijenjaju bodove. Konkurencija iz
          OpenStreetMapa samo se prikazuje i ne boduje se, jer popis možda nije potpun.
        </p>
      </section>

      <section className="card grid gap-2 p-5 text-sm text-muted">
        <h2 className="text-base font-semibold text-text">Karta i privatnost</h2>
        <p>
          Podloga karte je Protomaps izvadak podataka © OpenStreetMap contributors (ODbL), a
          granice četvrti su podaci Grada Zagreba. Fontovi karte: Noto Sans (SIL Open Font License).
          Udaljenosti su zračne, nisu vrijeme hoda.
        </p>
        <p>
          ProstorIQ ne traži račun, lokaciju uređaja ni osobne podatke i ne koristi kolačiće za
          praćenje. Spremljeni izračun otvara se samo uz pristupni ključ koji ostaje u ovoj kartici
          preglednika.
        </p>
      </section>
    </div>
  );
}
