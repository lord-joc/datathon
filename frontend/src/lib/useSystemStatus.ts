import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./api";

export interface SystemStatus {
  status: "ok" | "degraded";
  version: string;
  database: "up" | "down";
  postgis_version: string | null;
  dataset_ready: boolean;
  active_bundle_id: string | null;
  activated_at: string | null;
  message: string;
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: ({ signal }) => apiGet<SystemStatus>("/api/v1/status", { signal }),
    staleTime: 60_000,
    retry: 1,
  });
}
