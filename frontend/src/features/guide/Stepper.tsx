import { Check } from "lucide-react";

import { STEPS, type StepIndex } from "./store";

interface StepperProps {
  current: StepIndex;
  canOpen: (index: StepIndex) => boolean;
  onSelect: (index: StepIndex) => void;
}

export function Stepper({ current, canOpen, onSelect }: StepperProps) {
  return (
    <nav aria-label="Koraci vodiča">
      <ol className="grid grid-cols-4 gap-2">
        {STEPS.map((step, i) => {
          const index = i as StepIndex;
          const done = index < current;
          const active = index === current;
          const enabled = canOpen(index);
          return (
            <li key={step.id}>
              <button
                type="button"
                onClick={() => onSelect(index)}
                disabled={!enabled}
                aria-current={active ? "step" : undefined}
                className={[
                  "flex min-h-touch w-full flex-col items-start gap-1 border-t-2 pt-2 text-left text-sm transition-colors",
                  active
                    ? "border-accent text-text"
                    : done
                      ? "border-accent/50 text-muted"
                      : "border-border text-subtle",
                  enabled ? "cursor-pointer hover:text-text" : "cursor-not-allowed",
                ].join(" ")}
              >
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={[
                      "grid h-5 w-5 place-items-center rounded-full text-xs font-semibold",
                      active
                        ? "bg-accent text-bg"
                        : done
                          ? "bg-accent/20 text-accent"
                          : "bg-surface-2 text-subtle",
                    ].join(" ")}
                  >
                    {done ? <Check size={12} strokeWidth={3} /> : index + 1}
                  </span>
                  <span className="hidden sm:inline">{step.label}</span>
                </span>
                <span className="sr-only">
                  {`Korak ${index + 1}: ${step.label}${done ? ", dovršeno" : ""}`}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
