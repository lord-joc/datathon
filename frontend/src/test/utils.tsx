import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import type { Profile, Weights } from "@/lib/types";

export function renderApp(ui: ReactElement, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Routes fetch by path prefix to JSON bodies. Unknown paths answer 404 problem+json. */
export function mockApi(routes: Record<string, unknown>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const key = Object.keys(routes)
      .sort((a, b) => b.length - a.length)
      .find((k) => url.startsWith(k));
    if (key === undefined) {
      const problem = { status: 404, code: "NOT_FOUND", detail: "Nema." };
      return new Response(JSON.stringify(problem), { status: 404 });
    }
    return new Response(JSON.stringify(routes[key]), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export const weights = (o: Partial<Weights>): Weights => ({
  transit: 0,
  universities: 0,
  culture: 0,
  parking: 0,
  schools: 0,
  area: 0,
  street: 0,
  competition: 0,
  cost: 0,
  ...o,
});

export const CAFE_WEIGHTS = weights({
  transit: 20,
  universities: 10,
  culture: 10,
  parking: 5,
  area: 15,
  street: 10,
  competition: 10,
  cost: 20,
});

const profile = (
  code: Profile["profile"],
  name: string,
  icon: string,
  target: number,
  w: Weights,
  n: number,
): Profile => ({
  profile: code,
  profile_version: `00000000-0000-0000-0000-00000000000${n}`,
  version_label: "test",
  name,
  summary: `Sažetak: ${name}`,
  icon,
  target_area_m2: target,
  weights: w,
  competitor_categories: [],
  config_version: "ranking-3.1.0",
  cost_enabled: false,
});

export const PROFILES = {
  items: [
    profile("cafe", "Kafić / bar", "coffee", 60, CAFE_WEIGHTS, 1),
    profile("office", "Ured", "briefcase", 80, weights({ area: 25, parking: 15, cost: 30 }), 2),
    profile("retail", "Trgovina", "shopping-bag", 50, weights({ street: 20, cost: 20 }), 3),
    profile("food_takeaway", "Pekara / brza hrana", "croissant", 35, weights({ transit: 20 }), 4),
    profile("personal_care", "Salon", "scissors", 40, weights({ transit: 20 }), 5),
    profile(
      "education",
      "Edukacija / igraonica",
      "graduation-cap",
      100,
      weights({ schools: 25 }),
      6,
    ),
    profile("workshop", "Radionica / atelier", "hammer", 60, weights({ area: 30 }), 7),
  ],
};
