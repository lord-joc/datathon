import { TriangleAlert } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { CRITERION_LABEL, fmt0 } from "@/lib/labels";
import type { BasisChoice, BasisConflict } from "@/lib/types";

interface BasisDialogProps {
  conflict: BasisConflict;
  total: number;
  busy: boolean;
  onConfirm: (choice: BasisChoice) => void;
  onCancel: () => void;
}

const list = (items: string[]) => items.join(", ");

/**
 * 409 COMPARISON_BASIS_CHANGED: the user picks how to compare. Nothing is preselected and
 * the confirmation is valid for 10 minutes for this exact request (master prompt §2.2).
 */
export function BasisDialog({ conflict, total, busy, onConfirm, onCancel }: BasisDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [choice, setChoice] = useState<BasisChoice | null>(null);
  const titleId = useId();
  const incomplete = Object.keys(conflict.missing_by_space).length;
  const partial = conflict.partial_criteria.map((c) => CRITERION_LABEL[c]);
  const common = conflict.proposed_criteria.map((c) => CRITERION_LABEL[c]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog || dialog.open) return;
    // Modal (focus trap, Esc) where supported; a plain open dialog elsewhere.
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }, []);

  const options: { value: BasisChoice; title: string; text: string }[] = [
    {
      value: "common_criteria",
      title: `Usporedi svih ${fmt0(total)} po zajedničkim kriterijima`,
      text: common.length
        ? `Boduje se samo ${list(common)}. Pokrivenost odluke bit će manja.`
        : "Nijedan kriterij nije poznat svima, pa poredak neće imati rezultat.",
    },
    {
      value: "remove_incomplete",
      title: `Ukloni ${fmt0(incomplete)} nepotpunih i zadrži sve kriterije`,
      text: `U poretku ostaje ${fmt0(total - incomplete)} prostora. Uklonjeni ostaju na popisu s razlogom.`,
    },
  ];

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="m-auto w-[min(36rem,calc(100vw-32px))] rounded-card border border-border bg-surface p-0 text-text backdrop:bg-black/70"
    >
      <form
        method="dialog"
        className="grid gap-5 p-5 sm:p-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (choice) onConfirm(choice);
        }}
      >
        <header className="grid gap-2">
          <p className="flex items-center gap-2 text-sm font-semibold text-warn">
            <TriangleAlert aria-hidden="true" size={16} /> Promijenjena osnova usporedbe
          </p>
          <h2 id={titleId} className="font-display text-xl font-semibold">
            Za {fmt0(incomplete)} od {fmt0(total)} prostora nedostaju podaci
          </h2>
          <p className="text-sm text-muted">
            Nepoznato: {list(partial)}. Svi prostori moraju se uspoređivati po istim kriterijima, pa
            odaberite kako nastaviti.
          </p>
        </header>

        <fieldset className="grid gap-3">
          <legend className="sr-only">Način usporedbe</legend>
          {options.map((o) => (
            <label
              key={o.value}
              className={[
                "card spot flex cursor-pointer gap-3 p-4 has-[:focus-visible]:shadow-[var(--focus-ring)]",
                choice === o.value ? "border-accent bg-accent/10" : "hover:bg-surface-2",
              ].join(" ")}
            >
              <input
                type="radio"
                name="basis"
                value={o.value}
                checked={choice === o.value}
                onChange={() => setChoice(o.value)}
                className="mt-1 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]"
              />
              <span className="grid gap-1">
                <span className="font-medium">{o.title}</span>
                <span className="text-sm text-muted">{o.text}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <p className="text-xs text-subtle">
          Potvrda vrijedi {fmt0(Math.round(conflict.expires_in_s / 60))} minuta i samo za ovaj izbor
          prostora i postavki.
        </p>

        <div className="flex flex-wrap justify-end gap-3">
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Natrag na postavke
          </Button>
          <Button type="submit" disabled={!choice || busy}>
            {busy ? "Računam…" : "Potvrdi i izračunaj"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
