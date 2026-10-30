import { useEffect, useMemo, useState } from "react";

import { useProfiles, type SpaceFilter } from "@/lib/queries";
import type { Profile } from "@/lib/types";

import { useGuideStore } from "./store";

export function useDebounced<T>(value: T, ms = 200): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export function useActiveProfile(): Profile | undefined {
  const code = useGuideStore((s) => s.profile);
  const { data } = useProfiles();
  return data?.find((p) => p.profile === code);
}

/** The step-2 filters as sent to GET /spaces. Conditional spaces are always included. */
export function useSpaceFilter(): SpaceFilter | null {
  const profile = useGuideStore((s) => s.profile);
  const limitRange = useGuideStore((s) => s.limitRange);
  const areaMin = useGuideStore((s) => s.areaMin);
  const areaMax = useGuideStore((s) => s.areaMax);
  const districtIds = useGuideStore((s) => s.districtIds);
  return useMemo(
    () =>
      profile
        ? {
            profile,
            areaMin: limitRange ? areaMin : null,
            areaMax: limitRange ? areaMax : null,
            districtIds: [...districtIds].sort(),
            includeConditional: true,
          }
        : null,
    [profile, limitRange, areaMin, areaMax, districtIds],
  );
}
