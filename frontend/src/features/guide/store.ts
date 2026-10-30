import { create } from "zustand";

import { CRITERIA, type Criterion, type ProfileCode, type Radius, type Weights } from "@/lib/types";

export const STEPS = [
  { id: "djelatnost", label: "Djelatnost" },
  { id: "prostor", label: "Prostor" },
  { id: "prioriteti", label: "Prioriteti" },
  { id: "rezultati", label: "Rezultati" },
] as const;

export type StepIndex = 0 | 1 | 2 | 3;
export type Level = 0 | 1 | 2 | 3;
export type Levels = Record<Criterion, Level>;

/** Cost is never scored in the MVP; its weight stays as in the profile (coverage denominator). */
export const ADJUSTABLE: readonly Criterion[] = CRITERIA.filter((c) => c !== "cost");

const PROFILE_CODES: readonly ProfileCode[] = [
  "cafe",
  "office",
  "retail",
  "food_takeaway",
  "personal_care",
  "education",
  "workshop",
];

export interface GuideFilters {
  profile: ProfileCode | null;
  /** null = the profile's target area. */
  targetArea: number | null;
  limitRange: boolean;
  areaMin: number | null;
  areaMax: number | null;
  districtIds: string[];
  radius: Radius;
  /** Monthly rent budget in EUR; only compared with a known price, never with an estimate. */
  budget: number | null;
  /** null = recommended profile weights, sent unchanged. */
  levels: Levels | null;
}

interface GuideState extends GuideFilters {
  step: StepIndex;
  setProfile: (code: ProfileCode) => void;
  set: (patch: Partial<GuideFilters>) => void;
  setLevel: (criterion: Criterion, level: Level, defaults: Weights) => void;
  resetLevels: () => void;
  toggleDistrict: (id: string) => void;
  goTo: (step: StepIndex) => void;
  next: () => void;
  back: () => void;
}

export const INITIAL: GuideFilters = {
  profile: null,
  targetArea: null,
  limitRange: false,
  areaMin: null,
  areaMax: null,
  districtIds: [],
  radius: 500,
  budget: null,
  levels: null,
};

export const useGuideStore = create<GuideState>((set, get) => ({
  step: 0,
  ...INITIAL,
  // A new profile starts from its own recommended area and weights.
  setProfile: (code) =>
    set((s) =>
      s.profile === code
        ? {}
        : { profile: code, targetArea: null, areaMin: null, areaMax: null, levels: null },
    ),
  set: (patch) => set(patch),
  setLevel: (criterion, level, defaults) =>
    set((s) => ({ levels: { ...(s.levels ?? levelsFromWeights(defaults)), [criterion]: level } })),
  resetLevels: () => set({ levels: null }),
  toggleDistrict: (id) =>
    set((s) => ({
      districtIds: s.districtIds.includes(id)
        ? s.districtIds.filter((d) => d !== id)
        : [...s.districtIds, id],
    })),
  // A later step is reachable only once a profile is chosen.
  goTo: (step) => {
    if (step > 0 && get().profile === null) return;
    set({ step });
  },
  next: () => {
    const { step, profile } = get();
    if (step === 0 && profile === null) return;
    if (step < 3) set({ step: (step + 1) as StepIndex });
  },
  back: () => {
    const { step } = get();
    if (step > 0) set({ step: (step - 1) as StepIndex });
  },
}));

/** Profile weight -> importance level shown in step 3. */
export function levelFor(weight: number): Level {
  if (weight <= 0) return 0;
  if (weight < 10) return 1;
  if (weight < 20) return 2;
  return 3;
}

export function levelsFromWeights(weights: Weights): Levels {
  return Object.fromEntries(CRITERIA.map((c) => [c, levelFor(weights[c])])) as Levels;
}

/**
 * Custom levels -> weights normalised to 100 over the adjustable criteria, with cost keeping
 * the profile's share so coverage stays comparable with the recommended profile.
 */
export function weightsFromLevels(levels: Levels, defaults: Weights): Weights {
  const costShare = defaults.cost;
  const total = ADJUSTABLE.reduce((sum, c) => sum + levels[c], 0);
  const out = { cost: costShare } as Weights;
  for (const c of ADJUSTABLE) {
    out[c] = total === 0 ? 0 : Math.round((levels[c] / total) * (100 - costShare) * 100) / 100;
  }
  return out;
}

// --- URL state (filters only, never the ranking token) ---

const LEVEL_KEYS: Record<Criterion, string> = {
  transit: "t",
  universities: "u",
  culture: "k",
  parking: "g",
  schools: "s",
  area: "a",
  street: "l",
  competition: "c",
  cost: "x",
};

export function toSearch(f: GuideFilters, step: StepIndex): URLSearchParams {
  const q = new URLSearchParams();
  if (!f.profile) return q;
  q.set("djelatnost", f.profile);
  if (step > 0) q.set("korak", String(step + 1));
  if (f.targetArea !== null) q.set("m2", String(f.targetArea));
  if (f.limitRange) {
    if (f.areaMin !== null) q.set("od", String(f.areaMin));
    if (f.areaMax !== null) q.set("do", String(f.areaMax));
  }
  if (f.districtIds.length) q.set("cetvrti", f.districtIds.join(","));
  if (f.radius !== 500) q.set("radijus", String(f.radius));
  if (f.budget !== null) q.set("budzet", String(f.budget));
  if (f.levels) {
    q.set("vaznost", ADJUSTABLE.map((c) => `${LEVEL_KEYS[c]}${f.levels?.[c] ?? 0}`).join(""));
  }
  return q;
}

const num = (v: string | null, max = 100000): number | null => {
  if (v === null || v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= max ? n : null;
};

/** Parses untrusted URL parameters; anything invalid falls back to the default. */
export function fromSearch(q: URLSearchParams): { filters: GuideFilters; step: StepIndex } {
  const raw = q.get("djelatnost");
  const profile = PROFILE_CODES.includes(raw as ProfileCode) ? (raw as ProfileCode) : null;
  if (!profile) return { filters: INITIAL, step: 0 };
  const areaMin = num(q.get("od"));
  const areaMax = num(q.get("do"));
  let levels: Levels | null = null;
  const v = q.get("vaznost");
  if (v && /^([tukgsalc][0-3]){8}$/.test(v)) {
    levels = { cost: 3 } as Levels;
    for (const c of ADJUSTABLE) {
      const m = new RegExp(`${LEVEL_KEYS[c]}([0-3])`).exec(v);
      levels[c] = Number(m?.[1] ?? 0) as Level;
    }
  }
  const step = Number(q.get("korak") ?? "1") - 1;
  return {
    filters: {
      profile,
      targetArea: num(q.get("m2")),
      limitRange: areaMin !== null || areaMax !== null,
      areaMin,
      areaMax,
      districtIds: (q.get("cetvrti") ?? "")
        .split(",")
        .filter((d) => /^[0-9]{1,8}$/.test(d))
        .slice(0, 17),
      radius: q.get("radijus") === "1000" ? 1000 : 500,
      budget: num(q.get("budzet"), 1_000_000),
      levels,
    },
    step: (step >= 0 && step <= 3 ? step : 0) as StepIndex,
  };
}
