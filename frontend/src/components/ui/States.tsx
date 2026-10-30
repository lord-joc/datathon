import { CircleAlert, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";

import { errorMessage } from "@/lib/api";

import { Button } from "./Button";

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="card grid justify-items-start gap-3 p-5">
      <p className="flex items-start gap-2 text-sm">
        <CircleAlert aria-hidden="true" size={18} className="mt-0.5 shrink-0 text-danger" />
        <span>{errorMessage(error)}</span>
      </p>
      {onRetry && (
        <Button variant="ghost" onClick={onRetry}>
          <RotateCcw aria-hidden="true" size={16} /> Pokušaj ponovno
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card grid gap-2 p-5">
      <p className="font-medium">{title}</p>
      {children && <div className="text-sm text-muted">{children}</div>}
    </div>
  );
}

/** Placeholder that keeps the final layout while data loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div aria-hidden="true" className={`animate-pulse rounded-md bg-surface-2 ${className}`} />
  );
}
