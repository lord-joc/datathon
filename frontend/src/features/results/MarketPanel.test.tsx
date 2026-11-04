import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MarketSummary } from "@/lib/types";
import { mockApi, renderApp } from "@/test/utils";

import { chosenDistricts, marketHighlights, pendingNotices } from "./market";
import { MarketPanel } from "./MarketPanel";

const rent = (contracts: number, median: number | null) => ({
  contracts,
  median_eur_per_m2: median,
  p25_eur_per_m2: median,
  p75_eur_per_m2: median,
});

const MARKET: MarketSummary = {
  dataset_bundle_id: "b",
  profile: "cafe",
  competitor_categories: ["bar", "cafe"],
  city_rent: rent(12, 6.5),
  districts: [
    {
      district_id: "1",
      name: "Trnje",
      competitors: 40,
      competitors_per_km2: 5,
      rent: rent(2, null),
    },
    {
      district_id: "2",
      name: "Sesvete",
      competitors: 10,
      competitors_per_km2: 0.5,
      rent: rent(0, null),
    },
  ],
  lease_source_version_id: "v",
  lease_reference_period: "2024",
  pending_notices: 3,
  warnings: ["Zakupnine nisu tržišne cijene."],
};

describe("MarketPanel", () => {
  it("states facts about the extremes without calling either one better", () => {
    expect(marketHighlights(MARKET)).toEqual([
      "Najviše evidentiranih sličnih objekata po km²: Trnje (5,00).",
      "Najmanje: Sesvete (0,50).",
    ]);
  });

  it("names the user's own districts in the same terms and declines the plural", () => {
    expect(chosenDistricts(MARKET, ["2"])).toEqual([
      "Vaš odabir, Sesvete: 10 sličnih objekata, 0,50 po km².",
    ]);
    expect(pendingNotices(1)).toBe("1 obavijest Grada čeka provjeru tima.");
    expect(pendingNotices(14)).toBe("14 obavijesti Grada čeka provjeru tima.");
  });

  it("shows that it is not scored, the caveats and how many notices wait for review", async () => {
    mockApi({ "/api/v1/market": MARKET });
    renderApp(<MarketPanel profile="cafe" name="Kafić / bar" />);
    expect(await screen.findByText(/ne ulazi u bodove/i)).toBeInTheDocument();
    expect(screen.getByText(/nisu tržišne cijene/i)).toBeInTheDocument();
    expect(screen.getByText(/medijan 6,50 €/)).toBeInTheDocument();
    expect(screen.getByText(/3 obavijesti Grada čeka provjeru/)).toBeInTheDocument();
  });

  it("does not block the results when market data is unavailable", async () => {
    mockApi({});
    const { container } = renderApp(<MarketPanel profile="cafe" name="Kafić / bar" />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector("section")).toBeNull();
  });
});
