import { create } from "zustand";

import type { ProfileCode } from "./profiles";

export const STEPS = [
  { id: "djelatnost", label: "Djelatnost" },
  { id: "prostor", label: "Prostor" },
  { id: "prioriteti", label: "Prioriteti" },
  { id: "rezultati", label: "Rezultati" },
] as const;

export type StepIndex = 0 | 1 | 2 | 3;

interface GuideState {
  step: StepIndex;
  profile: ProfileCode | null;
  setProfile: (code: ProfileCode) => void;
  goTo: (step: StepIndex) => void;
  next: () => void;
  back: () => void;
}

export const useGuideStore = create<GuideState>((set, get) => ({
  step: 0,
  profile: null,
  setProfile: (code) => set({ profile: code }),
  // A later step is reachable only once the previous steps are complete.
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
