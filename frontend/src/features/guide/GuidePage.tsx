import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";

import { Button } from "@/components/ui/Button";
import { RunStep } from "@/features/results/RunStep";

import { useActiveProfile } from "./hooks";
import { PriorityStep } from "./PriorityStep";
import { ProfileStep } from "./ProfileStep";
import { SpaceStep } from "./SpaceStep";
import { Stepper } from "./Stepper";
import { ADJUSTABLE, fromSearch, toSearch, useGuideStore, type StepIndex } from "./store";

export function GuidePage() {
  const store = useGuideStore();
  const { step, profile, goTo, next, back } = store;
  const active = useActiveProfile();
  const [params, setParams] = useSearchParams();
  const restored = useRef(false);

  // Filters live in the URL so a link reproduces the guide (never the ranking token).
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (params.has("djelatnost")) {
      const { filters, step: s } = fromSearch(params);
      // Step 4 posts a new ranking; a shared link opens on the priorities instead.
      useGuideStore.setState({ ...filters, step: Math.min(s, 2) as StepIndex });
    }
  }, [params]);

  useEffect(() => {
    if (!restored.current) return;
    const next = toSearch(store, step).toString();
    if (next !== params.toString()) setParams(next, { replace: true });
  }, [store, step, params, setParams]);

  useEffect(() => {
    document.title = "ProstorIQ · Vodič";
  }, []);

  const canOpen = (index: StepIndex) => index === 0 || profile !== null;
  const noCriteria =
    step === 2 && store.levels !== null && ADJUSTABLE.every((c) => store.levels?.[c] === 0);
  const blocked = (step === 0 && profile === null) || (step === 1 && !active) || noCriteria;

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 py-6 sm:py-10">
      <Stepper current={step} canOpen={canOpen} onSelect={goTo} />

      <section className="sm:card sm:p-8">
        {step === 0 && <ProfileStep />}
        {step === 1 && <SpaceStep />}
        {step === 2 && <PriorityStep />}
        {step === 3 && <RunStep />}

        {step < 3 && (
          <div className="mt-8 flex items-center justify-between gap-3">
            {step > 0 ? (
              <Button variant="ghost" onClick={back}>
                <ArrowLeft aria-hidden="true" size={16} /> Natrag
              </Button>
            ) : (
              <span />
            )}
            <Button onClick={next} disabled={blocked}>
              {step === 2 ? "Prikaži rezultate" : "Dalje"}
              <ArrowRight aria-hidden="true" size={16} />
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
