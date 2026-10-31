/** TanStack Query hooks for the public API. Reference data is cached for the session. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet } from "./api";
import type {
  CompetitionResponse,
  District,
  DistrictLayer,
  PointLayerName,
  Profile,
  ProfileCode,
  Radius,
  RankingResponse,
  SourceList,
  SpaceDetail,
  SpaceList,
  SpaceSummary,
} from "./types";

const REFERENCE = { staleTime: 5 * 60_000, gcTime: 30 * 60_000 } as const;

export function useProfiles() {
  return useQuery({
    queryKey: ["profiles"],
    queryFn: ({ signal }) => apiGet<{ items: Profile[] }>("/api/v1/profiles", { signal }),
    select: (d) => d.items,
    ...REFERENCE,
  });
}

export function useDistricts() {
  return useQuery({
    queryKey: ["districts"],
    queryFn: ({ signal }) =>
      apiGet<{ dataset_bundle_id: string; items: District[] }>("/api/v1/districts", { signal }),
    ...REFERENCE,
  });
}

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: ({ signal }) => apiGet<SourceList>("/api/v1/sources", { signal }),
    ...REFERENCE,
  });
}

export function useDistrictLayer() {
  return useQuery({
    queryKey: ["layer", "districts"],
    queryFn: ({ signal }) => apiGet<DistrictLayer>("/api/v1/layers/districts", { signal }),
    ...REFERENCE,
  });
}

export function usePointLayer(layer: PointLayerName, enabled: boolean) {
  return useQuery({
    queryKey: ["layer", layer],
    queryFn: ({ signal }) =>
      apiGet<GeoJSON.FeatureCollection<GeoJSON.Point>>(`/api/v1/layers/${layer}`, { signal }),
    enabled,
    ...REFERENCE,
  });
}

export interface SpaceFilter {
  profile: ProfileCode;
  areaMin: number | null;
  areaMax: number | null;
  districtIds: string[];
  includeConditional: boolean;
}

function spaceParams(f: SpaceFilter, page: number, pageSize: number): string {
  const q = new URLSearchParams({
    profile: f.profile,
    include_conditional: String(f.includeConditional),
    page: String(page),
    page_size: String(pageSize),
  });
  if (f.areaMin !== null) q.set("area_min_m2", String(f.areaMin));
  if (f.areaMax !== null) q.set("area_max_m2", String(f.areaMax));
  for (const id of f.districtIds) q.append("district_ids", id);
  return q.toString();
}

/** Live counter in step 2: one tiny page is enough, the total comes with it. */
export function useSpaceCount(filter: SpaceFilter | null) {
  return useQuery({
    queryKey: ["space-count", filter],
    queryFn: ({ signal }) =>
      apiGet<SpaceList>(`/api/v1/spaces?${spaceParams(filter as SpaceFilter, 1, 1)}`, {
        signal,
      }),
    enabled: filter !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/** Every matching space (at most 500 can be ranked), fetched page by page. */
export async function fetchAllSpaces(
  filter: SpaceFilter,
  signal?: AbortSignal,
): Promise<{ items: SpaceSummary[]; bundleId: string; warnings: string[] }> {
  const items: SpaceSummary[] = [];
  let page = 1;
  for (;;) {
    const body = await apiGet<SpaceList>(`/api/v1/spaces?${spaceParams(filter, page, 100)}`, {
      ...(signal ? { signal } : {}),
    });
    items.push(...body.items);
    if (items.length >= body.total || body.items.length === 0 || items.length >= 500) {
      return { items, bundleId: body.dataset_bundle_id, warnings: body.warnings };
    }
    page += 1;
  }
}

export function useSpaceDetail(spaceId: string, profile: ProfileCode, radius: Radius) {
  return useQuery({
    queryKey: ["space", spaceId, profile, radius],
    queryFn: ({ signal }) =>
      apiGet<SpaceDetail>(`/api/v1/spaces/${spaceId}?profile=${profile}&radius_m=${radius}`, {
        signal,
      }),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
}

export function useCompetitors(
  spaceId: string,
  bundleId: string,
  profile: ProfileCode,
  radius: Radius,
) {
  return useQuery({
    queryKey: ["competitors", spaceId, bundleId, profile, radius],
    queryFn: ({ signal }) =>
      apiGet<CompetitionResponse>(
        `/api/v1/spaces/${spaceId}/competitors?dataset_bundle_id=${bundleId}` +
          `&profile=${profile}&radius_m=${radius}&page_size=100`,
        { signal },
      ),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
}

const TOKEN_PREFIX = "prostoriq.ranking.";

/** The access token lives only in sessionStorage (master prompt §6.1), never in the URL. */
export const rankingToken = {
  save(runId: string, token: string) {
    try {
      sessionStorage.setItem(TOKEN_PREFIX + runId, token);
    } catch {
      /* private mode: the run stays available until the tab is reloaded */
    }
  },
  get(runId: string): string | null {
    try {
      return sessionStorage.getItem(TOKEN_PREFIX + runId);
    } catch {
      return null;
    }
  },
};

export function useRanking(runId: string) {
  return useQuery({
    queryKey: ["ranking", runId],
    queryFn: ({ signal }) => {
      const token = rankingToken.get(runId) ?? "";
      return apiGet<RankingResponse>(`/api/v1/rankings/${runId}`, {
        signal,
        headers: { "X-Ranking-Token": token },
      });
    },
    enabled: runId !== "",
    staleTime: Infinity,
    retry: false,
  });
}
