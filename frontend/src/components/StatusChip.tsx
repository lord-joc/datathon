import { CircleCheck, CircleHelp, CircleX } from "lucide-react";

import { STATUS_LABEL } from "@/lib/labels";
import type { CandidateStatus } from "@/lib/types";

const STYLE: Record<CandidateStatus, { icon: typeof CircleCheck; tone: string }> = {
  ready: { icon: CircleCheck, tone: "border-ok/40 text-ok" },
  conditional: { icon: CircleHelp, tone: "border-warn/40 text-warn" },
  excluded: { icon: CircleX, tone: "border-danger/40 text-danger" },
};

/** Status is never colour alone: icon + text + colour (master prompt §7.2). */
export function StatusChip({ status }: { status: CandidateStatus }) {
  const { icon: Icon, tone } = STYLE[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${tone}`}
    >
      <Icon aria-hidden="true" size={13} />
      {STATUS_LABEL[status]}
    </span>
  );
}
