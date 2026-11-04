import { CircleAlert, CircleDashed, LoaderCircle } from "lucide-react";

import { useSystemStatus } from "@/lib/useSystemStatus";

/**
 * Data status on the red header bar. When everything is ready it stays silent (a calm header);
 * a problem shows as a white pill with text, so it never relies on colour.
 */
export function SystemStatusBadge() {
  const { data, isPending, isError } = useSystemStatus();

  if (!isPending && !isError && data && data.database !== "down" && data.dataset_ready) {
    return (
      <span role="status" className="sr-only">
        Podaci spremni
      </span>
    );
  }

  let icon = <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />;
  let label = "Provjera…";
  if (!isPending) {
    if (isError || !data || data.database === "down") {
      icon = <CircleAlert size={14} aria-hidden="true" />;
      label = "Poslužitelj nedostupan";
    } else {
      icon = <CircleDashed size={14} aria-hidden="true" />;
      label = "Podaci nisu uvezeni";
    }
  }

  return (
    <span
      role="status"
      title={data?.message ?? label}
      className="mr-1 hidden items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 text-xs font-medium sm:inline-flex"
    >
      {icon}
      {label}
    </span>
  );
}
