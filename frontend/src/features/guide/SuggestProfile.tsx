import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { apiPost, errorMessage } from "@/lib/api";
import { CRITERION_LABEL, TOPIC_LABEL, fmt0, fmt2 } from "@/lib/labels";
import type { BusinessBrief, Profile, ProfileCode } from "@/lib/types";

import { useGuideStore } from "./store";

const MIN = 5;
const MAX = 500;

/** "Nešto drugo?": local proposals from the user's own words; the user always decides (ADR24). */
export function SuggestProfile({ profiles }: { profiles: Profile[] }) {
  const inputId = useId();
  const [text, setText] = useState("");
  const applyBrief = useGuideStore((s) => s.applyBrief);
  const brief = useMutation({
    mutationFn: (description: string) =>
      apiPost<BusinessBrief>("/api/v1/business-brief", { description }),
  });
  const profileOf = (code: ProfileCode) => profiles.find((p) => p.profile === code);
  const name = (code: ProfileCode) => profileOf(code)?.name ?? code;
  const trimmed = text.trim();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (trimmed.length >= MIN) brief.mutate(trimmed);
  };

  const choose = (code: ProfileCode) => {
    const profile = profileOf(code);
    if (profile && brief.data) applyBrief(code, brief.data, profile.weights);
  };

  const data = brief.data;
  const suggestion = data?.suggestion;
  const hasFacts =
    data &&
    (data.area_m2 !== null ||
      data.budget_eur !== null ||
      data.districts.length > 0 ||
      data.priorities.length > 0);
  return (
    <section className="card grid gap-3 p-4" aria-labelledby={`${inputId}-title`}>
      <h2 id={`${inputId}-title`} className="flex items-center gap-2 font-medium">
        <Sparkles aria-hidden="true" size={16} className="text-accent" /> Nešto drugo?
      </h2>
      <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <label htmlFor={inputId} className="sr-only">
          Opišite djelatnost
        </label>
        <textarea
          id={inputId}
          rows={2}
          value={text}
          maxLength={MAX}
          onChange={(e) => setText(e.target.value)}
          placeholder="Npr. mala kavana oko 45 m² za studente blizu tramvaja, na Trešnjevci, parking nije bitan"
          className="min-h-touch rounded-md border border-border bg-bg px-3 py-2 text-base"
        />
        <Button type="submit" variant="ghost" disabled={trimmed.length < MIN || brief.isPending}>
          {brief.isPending ? "Tražim…" : "Predloži djelatnost"}
        </Button>
      </form>
      <p className="text-xs text-subtle">
        Lokalni AI model i pravila čitaju opis bez slanja trećima. Opis se ne sprema. Vi birate
        djelatnost, a prijedlog se primjenjuje tek kad ga odaberete.
      </p>

      <div aria-live="polite" className="grid gap-3">
        {brief.isError && <p className="text-sm text-danger">{errorMessage(brief.error)}</p>}
        {data && suggestion && (
          <>
            <p className="text-sm">
              {suggestion.status === "suggested" && suggestion.suggested_profile ? (
                <>
                  Prijedlog: <strong>{name(suggestion.suggested_profile)}</strong>. Odgovara li?
                </>
              ) : (
                <>
                  Nismo sigurni koja djelatnost odgovara. Ako nijedna od najsličnijih ne odgovara,
                  ProstorIQ za nju još nema provjerena pravila.
                </>
              )}
            </p>

            {hasFacts && (
              <div className="grid gap-1 rounded-md bg-surface-2 p-3 text-sm">
                <p className="font-medium">Iz vašeg opisa prenijet ćemo:</p>
                <ul className="grid gap-1 text-muted">
                  {data.area_m2 !== null && <li>Ciljna površina {fmt0(data.area_m2)} m²</li>}
                  {data.budget_eur !== null && (
                    <li>Budžet do {fmt0(data.budget_eur)} € mjesečno</li>
                  )}
                  {data.districts.length > 0 && (
                    <li>Četvrti: {data.districts.map((d) => d.name).join(", ")}</li>
                  )}
                  {data.priorities.map((p) => (
                    <li key={p.criterion}>
                      {CRITERION_LABEL[p.criterion]}: {p.level === 0 ? "nevažno" : "vrlo važno"},
                      jer ste napisali „{p.words}”
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <ul className="grid gap-2">
              {suggestion.candidates.map((c) => (
                <li key={c.profile} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm">
                    {name(c.profile)}{" "}
                    <span className="text-subtle">· sličnost {fmt2(c.similarity)}</span>
                  </span>
                  <Button
                    variant={c.profile === suggestion.suggested_profile ? "primary" : "ghost"}
                    onClick={() => choose(c.profile)}
                  >
                    Odaberi {name(c.profile)}
                  </Button>
                </li>
              ))}
            </ul>

            {data.notices.length > 0 && (
              <div className="grid gap-1 text-sm">
                <p className="font-medium">Obavijesti Grada bliske vašem opisu</p>
                <ul className="grid gap-2 text-muted">
                  {data.notices.map((n) => (
                    <li key={n.card_id}>
                      <span className="text-subtle">{TOPIC_LABEL[n.topic]}:</span> {n.summary}{" "}
                      <a
                        href={n.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-accent hover:underline"
                      >
                        Izvor
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <details className="text-xs text-subtle">
              <summary className="min-h-touch cursor-pointer py-2">Kako je izračunato</summary>
              <ul className="grid gap-1">
                {suggestion.candidates.map((c) => (
                  <li key={c.profile}>
                    {name(c.profile)}: {fmt2(c.similarity)}, najbliži primjer „{c.matched_example}”
                  </li>
                ))}
              </ul>
              <p className="mt-2">
                Model {suggestion.model_id} (revizija {suggestion.model_revision.slice(0, 7)}),
                lokalno, bez slanja trećima. Prijedlog se daje samo uz sličnost od barem{" "}
                {fmt2(suggestion.min_similarity)} i prednost od barem {fmt2(suggestion.min_margin)}{" "}
                pred drugom djelatnošću. Pragovi su podešeni na malom skupu primjera (36), pa model
                može pogriješiti. Površinu, budžet, četvrti i važnost kriterija čitaju pravila iz
                riječi koje ste napisali, a sve možete promijeniti u sljedećim koracima.
              </p>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
