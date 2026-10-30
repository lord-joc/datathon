import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useActiveProfile, useSpaceFilter } from "@/features/guide/hooks";
import { useGuideStore, weightsFromLevels } from "@/features/guide/store";
import { ApiError, apiPost } from "@/lib/api";
import { fetchAllSpaces, rankingToken } from "@/lib/queries";
import type { BasisChoice, BasisConflict, RankingRequest, RankingResponse } from "@/lib/types";

export type RunOutcome =
  | { kind: "done"; run: RankingResponse }
  | { kind: "conflict"; conflict: BasisConflict; request: RankingRequest; total: number }
  | { kind: "empty" };

/** Builds the ranking request from the guide and posts it; a 409 is returned, not thrown. */
export function useRunRanking() {
  const queryClient = useQueryClient();
  const profile = useActiveProfile();
  const filter = useSpaceFilter();
  const { targetArea, radius, levels } = useGuideStore();

  return useMutation({
    mutationFn: async (confirm?: {
      request: RankingRequest;
      token: string;
      choice: BasisChoice;
    }): Promise<RunOutcome> => {
      let request: RankingRequest;
      if (confirm) {
        request = {
          ...confirm.request,
          comparison_basis_token: confirm.token,
          basis_choice: confirm.choice,
        };
      } else {
        if (!profile || !filter) throw new Error("Odaberite djelatnost.");
        const { items, bundleId } = await fetchAllSpaces(filter);
        if (items.length === 0) return { kind: "empty" };
        const weights = levels ? weightsFromLevels(levels, profile.weights) : undefined;
        request = {
          profile: profile.profile,
          profile_version: profile.profile_version,
          dataset_bundle_id: bundleId,
          space_ids: items.map((s) => s.space_id),
          radius_m: radius,
          prefer_lower_competition: (weights ?? profile.weights).competition > 0,
          include_conditional: true,
          missing_policy: "require_ack",
          ...(targetArea !== null ? { target_area_m2: targetArea } : {}),
          ...(weights ? { weights } : {}),
        };
      }
      try {
        const run = await apiPost<RankingResponse>("/api/v1/rankings", request);
        if (run.access_token) rankingToken.save(run.ranking_run_id, run.access_token);
        queryClient.setQueryData(["ranking", run.ranking_run_id], run);
        return { kind: "done", run };
      } catch (error) {
        if (error instanceof ApiError && error.problem.code === "COMPARISON_BASIS_CHANGED") {
          return {
            kind: "conflict",
            conflict: error.problem as unknown as BasisConflict,
            request,
            total: request.space_ids.length,
          };
        }
        throw error;
      }
    },
  });
}
