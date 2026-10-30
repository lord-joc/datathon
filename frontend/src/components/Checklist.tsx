import { ExternalLink, ListChecks } from "lucide-react";

/** "Popis za provjeru" (master prompt §6.1). Only official home pages, no guessed deep links. */
const STEPS = [
  {
    title: "Provjerite natječaj",
    text: "Je li prostor raspisan u aktualnom natječaju za zakup gradskih poslovnih prostora i do kada traju prijave.",
    href: "https://www.zagreb.hr",
    link: "zagreb.hr",
  },
  {
    title: "Provjerite namjenu",
    text: "Dopušta li prostorni plan (GUP) vašu djelatnost na toj lokaciji.",
    href: "https://geoportal.zagreb.hr",
    link: "Geoportal Grada Zagreba",
  },
  {
    title: "Obiđite prostor",
    text: "Stanje, ulaz, izlog, sanitarni čvor i tehnički uvjeti (struja, ventilacija, pristup).",
  },
  {
    title: "Pripremite pokretanje poslovanja",
    text: "Službene e-usluge za osnivanje i registraciju djelatnosti.",
    href: "https://gov.hr",
    link: "gov.hr (e-Građani)",
  },
] as const;

export function Checklist({ title = "Popis za provjeru" }: { title?: string }) {
  return (
    <section className="card grid gap-4 p-5" aria-labelledby="checklist-title">
      <h2 id="checklist-title" className="flex items-center gap-2 text-lg font-semibold">
        <ListChecks aria-hidden="true" size={18} className="text-accent" /> {title}
      </h2>
      <ol className="grid gap-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            <span
              aria-hidden="true"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-semibold text-muted"
            >
              {i + 1}
            </span>
            <span className="grid gap-0.5 text-sm">
              <span className="font-medium">{s.title}</span>
              <span className="text-muted">{s.text}</span>
              {"href" in s && (
                <a
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-h-touch items-center gap-1 text-accent hover:underline"
                >
                  {s.link} <ExternalLink aria-hidden="true" size={13} />
                  <span className="sr-only">(otvara se u novoj kartici)</span>
                </a>
              )}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
