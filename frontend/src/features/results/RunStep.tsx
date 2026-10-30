import { LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState } from "@/components/ui/States";
import { useGuideStore } from "@/features/guide/store";

import { BasisDialog } from "./BasisDialog";
import { useRunRanking, type RunOutcome } from "./runRanking";

/** Step 4 of the guide: posts the ranking, handles 409 and opens the saved run. */
export function RunStep() {
  const navigate = useNavigate();
  const back = useGuideStore((s) => s.back);
  const budget = useGuideStore((s) => s.budget);
  const run = useRunRanking();
  const [outcome, setOutcome] = useState<RunOutcome | null>(null);
  const started = useRef(false);

  const handle = (o: RunOutcome) => {
    if (o.kind === "done") {
      navigate(`/rezultati/${o.run.ranking_run_id}${budget !== null ? `?budzet=${budget}` : ""}`);
    } else setOutcome(o);
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    run.mutate(undefined, { onSuccess: handle });
    // Runs once when the step opens; a retry is explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (run.isError) {
    return (
      <ErrorState error={run.error} onRetry={() => run.mutate(undefined, { onSuccess: handle })} />
    );
  }
  if (outcome?.kind === "empty") {
    return (
      <EmptyState title="Nijedan prostor ne odgovara odabiru">
        Uklonite raspon površine ili odaberite više četvrti.
        <div className="mt-3">
          <Button variant="ghost" onClick={back}>
            Natrag na prostor
          </Button>
        </div>
      </EmptyState>
    );
  }

  return (
    <div className="grid min-h-[12rem] place-items-center gap-3 text-center" aria-busy="true">
      <p className="flex items-center gap-2 text-muted" role="status">
        <LoaderCircle aria-hidden="true" size={18} className="animate-spin text-accent" />
        {outcome?.kind === "conflict" ? "Čeka se vaš odabir…" : "Uspoređujem prostore…"}
      </p>
      {outcome?.kind === "conflict" && (
        <BasisDialog
          key={outcome.conflict.comparison_basis_token}
          conflict={outcome.conflict}
          total={outcome.total}
          busy={run.isPending}
          onCancel={() => {
            setOutcome(null);
            back();
          }}
          onConfirm={(choice) =>
            run.mutate(
              { request: outcome.request, token: outcome.conflict.comparison_basis_token, choice },
              { onSuccess: handle },
            )
          }
        />
      )}
    </div>
  );
}
