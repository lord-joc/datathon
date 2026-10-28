import { CircleAlert, CircleCheck, CircleDashed, LoaderCircle } from "lucide-react";

import { useSystemStatus } from "@/lib/useSystemStatus";

export function SystemStatusBadge() {
  const { data, isPending, isError } = useSystemStatus();

  let icon = <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />;
  let label = "Provjera…";
  let tone = "text-subtle";

  if (!isPending) {
    if (isError || !data || data.database === "down") {
      icon = <CircleAlert size={14} aria-hidden="true" />;
      label = "Poslužitelj nedostupan";
      tone = "text-danger";
    } else if (!data.dataset_ready) {
      icon = <CircleDashed size={14} aria-hidden="true" />;
      label = "Podaci nisu uvezeni";
      tone = "text-warn";
    } else {
      icon = <CircleCheck size={14} aria-hidden="true" />;
      label = "Podaci spremni";
      tone = "text-ok";
    }
  }

  return (
    <span
      role="status"
      title={data?.message ?? label}
      className={`hidden items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs sm:inline-flex ${tone}`}
    >
      {icon}
      {label}
    </span>
  );
}
