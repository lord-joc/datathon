import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { apiPost, errorMessage } from "@/lib/api";
import { fmt2 } from "@/lib/labels";
import type { Profile, ProfileCode, ProfileSuggestion } from "@/lib/types";

const MIN = 5;
const MAX = 500;

/** "Nešto drugo?": the local model suggests, the user always decides (FZ25, ADR21). */
export function SuggestProfile({
  profiles,
  onChoose,
}: {
  profiles: Profile[];
  onChoose: (code: ProfileCode) => void;
}) {
  const inputId = useId();
  const [text, setText] = useState("");
  const suggest = useMutation({
    mutationFn: (description: string) =>
      apiPost<ProfileSuggestion>("/api/v1/profile-suggestions", { description }),
  });
  const name = (code: ProfileCode) => profiles.find((p) => p.profile === code)?.name ?? code;
  const trimmed = text.trim();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (trimmed.length >= MIN) suggest.mutate(trimmed);
  };

  const data = suggest.data;
  return (
    <section className="card grid gap-3 p-4" aria-labelledby={`${inputId}-title`}>
      <h2 id={`${inputId}-title`} className="flex items-center gap-2 font-medium">
        <Sparkles aria-hidden="true" size={16} className="text-accent" /> Nešto drugo?
      </h2>
      <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_auto]">
        <label htmlFor={inputId} className="sr-only">
          Opišite djelatnost
        </label>
        <input
          id={inputId}
          type="text"
          value={text}
          maxLength={MAX}
          onChange={(e) => setText(e.target.value)}
          placeholder="Npr. mala kavana s terasom ili radionica za popravak bicikala"
          className="min-h-touch rounded-md border border-border bg-bg px-3 text-base"
        />
        <Button type="submit" variant="ghost" disabled={trimmed.length < MIN || suggest.isPending}>
          {suggest.isPending ? "Tražim…" : "Predloži djelatnost"}
        </Button>
      </form>
      <p className="text-xs text-subtle">
        Lokalni AI model uspoređuje opis s primjerima podržanih djelatnosti. Opis se ne sprema. Vi
        birate djelatnost, a prijedlog ne mijenja bodove.
      </p>

      <div aria-live="polite" className="grid gap-2">
        {suggest.isError && <p className="text-sm text-danger">{errorMessage(suggest.error)}</p>}
        {data && (
          <>
            <p className="text-sm">
              {data.status === "suggested" && data.suggested_profile ? (
                <>
                  Prijedlog: <strong>{name(data.suggested_profile)}</strong>. Odgovara li?
                </>
              ) : (
                <>
                  Nismo sigurni koja djelatnost odgovara. Ako nijedna od najsličnijih ne odgovara,
                  ProstorIQ za nju još nema provjerena pravila.
                </>
              )}
            </p>
            <ul className="grid gap-2">
              {data.candidates.map((c) => (
                <li key={c.profile} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm">
                    {name(c.profile)}{" "}
                    <span className="text-subtle">· sličnost {fmt2(c.similarity)}</span>
                  </span>
                  <Button
                    variant={c.profile === data.suggested_profile ? "primary" : "ghost"}
                    onClick={() => onChoose(c.profile)}
                  >
                    Odaberi {name(c.profile)}
                  </Button>
                </li>
              ))}
            </ul>
            <details className="text-xs text-subtle">
              <summary className="min-h-touch cursor-pointer py-2">Kako je izračunato</summary>
              <ul className="grid gap-1">
                {data.candidates.map((c) => (
                  <li key={c.profile}>
                    {name(c.profile)}: {fmt2(c.similarity)}, najbliži primjer „{c.matched_example}”
                  </li>
                ))}
              </ul>
              <p className="mt-2">
                Model {data.model_id} (revizija {data.model_revision.slice(0, 7)}), lokalno, bez
                slanja trećima. Prijedlog se daje samo uz sličnost od barem{" "}
                {fmt2(data.min_similarity)} i prednost od barem {fmt2(data.min_margin)} pred drugom
                djelatnošću. Pragovi su podešeni na malom skupu primjera (36), pa model može
                pogriješiti.
              </p>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
