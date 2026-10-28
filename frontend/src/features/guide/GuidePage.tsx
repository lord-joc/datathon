import { ArrowLeft, ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/Button";

import { ProfileStep } from "./ProfileStep";
import { Stepper } from "./Stepper";
import { STEPS, useGuideStore, type StepIndex } from "./store";

export function GuidePage() {
  const { step, profile, goTo, next, back } = useGuideStore();
  const canOpen = (index: StepIndex) => index === 0 || profile !== null;

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 py-6 sm:py-10">
      <Stepper current={step} canOpen={canOpen} onSelect={goTo} />

      <section className="card p-5 sm:p-8" aria-live="polite">
        {step === 0 ? (
          <ProfileStep />
        ) : (
          <div className="grid gap-2">
            <p className="eyebrow">Korak {step + 1}</p>
            <h1 className="font-display text-2xl font-semibold">{STEPS[step].label}</h1>
            <p className="text-muted">Ovaj korak dolazi u sljedećim isječcima.</p>
          </div>
        )}

        <div className="mt-8 flex items-center justify-between gap-3">
          {step > 0 ? (
            <Button variant="ghost" onClick={back}>
              <ArrowLeft aria-hidden="true" size={16} /> Natrag
            </Button>
          ) : (
            <span />
          )}
          {step < 3 && (
            <Button onClick={next} disabled={step === 0 && profile === null}>
              Dalje <ArrowRight aria-hidden="true" size={16} />
            </Button>
          )}
        </div>
      </section>
    </div>
  );
}
