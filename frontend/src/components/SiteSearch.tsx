/**
 * Header search over activities (profiles) and spaces (address, street, district, ID).
 * The space list (262 rows) is fetched once, on first focus, and filtered in the browser, so
 * typing never sends a request. ARIA combobox with a listbox: arrows, Enter, Escape.
 */
import { useQuery } from "@tanstack/react-query";
import { Building2, Search, X } from "lucide-react";
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";

import { profileIcon } from "@/features/guide/profiles";
import { useGuideStore } from "@/features/guide/store";
import { apiGet } from "@/lib/api";
import { fmt0, prettyAddress } from "@/lib/labels";
import { matchScore, normalize } from "@/lib/text";
import { useProfiles } from "@/lib/queries";
import type { ProfileCode, SpaceList, SpaceSummary } from "@/lib/types";

const MAX_SPACES = 6;
const MAX_PROFILES = 3;

async function fetchSearchSpaces(signal: AbortSignal): Promise<SpaceSummary[]> {
  const items: SpaceSummary[] = [];
  for (let page = 1; page <= 10; page++) {
    const q = new URLSearchParams({
      profile: "office",
      include_conditional: "true",
      include_excluded: "true",
      page: String(page),
      page_size: "100",
    });
    const body = await apiGet<SpaceList>(`/api/v1/spaces?${q.toString()}`, { signal });
    items.push(...body.items);
    if (items.length >= body.total || body.items.length === 0) break;
  }
  return items;
}

type Option =
  | { kind: "profile"; key: string; code: ProfileCode; label: string; hint: string; icon: string }
  | { kind: "space"; key: string; id: string; label: string; hint: string };

export function SiteSearch({ className = "" }: { className?: string }) {
  const id = useId();
  const listId = `${id}-list`;
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [wanted, setWanted] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const profiles = useProfiles();
  const spaces = useQuery({
    queryKey: ["search-spaces"],
    queryFn: ({ signal }) => fetchSearchSpaces(signal),
    enabled: wanted,
    staleTime: 10 * 60_000,
  });

  const index = useMemo(
    () =>
      (spaces.data ?? []).map((s) => ({
        space: s,
        words: normalize(`${s.address} ${s.district_name ?? ""} ${s.space_id}`).split(" "),
      })),
    [spaces.data],
  );

  const options = useMemo<Option[]>(() => {
    const words = normalize(query).split(" ").filter(Boolean);
    if (words.length === 0) return [];
    const found: Option[] = (profiles.data ?? [])
      .map((p) => ({ p, score: matchScore(words, normalize(`${p.name} ${p.summary}`).split(" ")) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_PROFILES)
      .map(({ p }) => ({
        kind: "profile",
        key: `p-${p.profile}`,
        code: p.profile,
        label: p.name,
        hint: "Djelatnost: pokreni Vodič",
        icon: p.icon,
      }));
    const spaceHits = index
      .map(({ space, words: w }) => ({ space, score: matchScore(words, w) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_SPACES);
    for (const { space } of spaceHits) {
      const area =
        space.area.value !== null ? `${fmt0(space.area.value)} m²` : "površina nepoznata";
      found.push({
        kind: "space",
        key: `s-${space.space_id}`,
        id: space.space_id,
        label: prettyAddress(space.address),
        hint: [space.district_name, area].filter(Boolean).join(", "),
      });
    }
    return found;
  }, [query, profiles.data, index]);

  const choose = (option: Option) => {
    setOpen(false);
    setQuery("");
    input.current?.blur();
    if (option.kind === "profile") {
      const store = useGuideStore.getState();
      store.setProfile(option.code);
      store.goTo(1);
      void navigate(`/?djelatnost=${option.code}&korak=2`);
    } else {
      const profile = useGuideStore.getState().profile ?? "cafe";
      void navigate(`/prostor/${option.id}?djelatnost=${profile}`);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      if (options.length === 0) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => (a + step + options.length) % options.length);
    } else if (e.key === "Enter") {
      const option = options[active];
      if (open && option) {
        e.preventDefault();
        choose(option);
      }
    } else if (e.key === "Escape") {
      if (query) setQuery("");
      else input.current?.blur();
      setOpen(false);
    }
  };

  const showPanel = open && normalize(query) !== "";
  const loading = spaces.isPending && wanted;
  const activeKey = showPanel ? options[active]?.key : undefined;

  return (
    <div className={`relative ${className}`}>
      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const option = options[active];
          if (option) choose(option);
        }}
        className="flex h-11 items-center rounded-md bg-surface text-text ring-1 ring-inset ring-black/5 focus-within:ring-2 focus-within:ring-on-bar"
      >
        <label htmlFor={`${id}-input`} className="sr-only">
          Pretraži prostore i djelatnosti
        </label>
        <Search aria-hidden="true" size={18} className="ml-3 shrink-0 text-subtle" />
        <input
          ref={input}
          id={`${id}-input`}
          type="search"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeKey ? `${id}-${activeKey}` : undefined}
          autoComplete="off"
          enterKeyHint="search"
          placeholder="Adresa, četvrt ili djelatnost"
          value={query}
          maxLength={80}
          onFocus={() => {
            setWanted(true);
            setOpen(true);
          }}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
          className="h-full min-w-0 flex-1 bg-transparent px-2 text-base placeholder:text-subtle focus:outline-none focus-visible:shadow-none [&::-webkit-search-cancel-button]:hidden"
        />
        {query && (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              setQuery("");
              input.current?.focus();
            }}
            className="grid h-11 w-11 shrink-0 place-items-center text-subtle hover:text-text"
            aria-label="Obriši pretragu"
          >
            <X aria-hidden="true" size={18} />
          </button>
        )}
      </form>

      {showPanel && (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-md border border-border bg-surface text-text shadow-lg">
          <ul
            id={listId}
            role="listbox"
            aria-label="Rezultati pretrage"
            className="max-h-[60vh] overflow-y-auto py-1"
          >
            {options.map((o, i) => {
              const Icon = o.kind === "profile" ? profileIcon(o.icon) : Building2;
              const selected = i === active;
              return (
                <li
                  key={o.key}
                  id={`${id}-${o.key}`}
                  role="option"
                  aria-selected={selected}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(o)}
                  className={[
                    "flex min-h-touch cursor-pointer items-center gap-3 border-l-2 px-3 py-2",
                    selected ? "border-accent bg-accent/[0.07]" : "border-transparent",
                  ].join(" ")}
                >
                  <Icon
                    aria-hidden="true"
                    size={18}
                    className={selected ? "shrink-0 text-accent" : "shrink-0 text-subtle"}
                  />
                  <span className="grid min-w-0">
                    <span className="truncate font-medium">{o.label}</span>
                    <span className="truncate text-sm text-muted">{o.hint}</span>
                  </span>
                </li>
              );
            })}
          </ul>
          {options.length === 0 && (
            <p className="px-4 py-3 text-sm text-muted" role="status">
              {loading
                ? "Učitavam popis prostora…"
                : spaces.isError
                  ? "Popis prostora trenutno nije dostupan. Pokušajte ponovno."
                  : "Nema prostora ni djelatnosti za taj upit. Probajte ulicu bez kućnog broja."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
