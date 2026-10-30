import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockApi, PROFILES, renderApp } from "@/test/utils";

import { GuidePage } from "./GuidePage";
import { INITIAL, useGuideStore } from "./store";

describe("GuidePage", () => {
  beforeEach(() => {
    useGuideStore.setState({ step: 0, ...INITIAL });
    mockApi({ "/api/v1/profiles": PROFILES });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows all seven profiles from the API", async () => {
    renderApp(<GuidePage />);
    expect(await screen.findAllByRole("radio")).toHaveLength(7);
    expect(screen.getByText("Ciljna površina 80 m²")).toBeInTheDocument();
  });

  it("blocks the next step until a profile is chosen", async () => {
    renderApp(<GuidePage />);
    const next = screen.getByRole("button", { name: /dalje/i });
    expect(next).toBeDisabled();

    fireEvent.click(await screen.findByRole("radio", { name: /ured/i }));
    expect(next).toBeEnabled();

    fireEvent.click(next);
    expect(useGuideStore.getState().step).toBe(1);
  });

  it("marks the current step for assistive technology", () => {
    renderApp(<GuidePage />);
    expect(screen.getByRole("button", { current: "step" })).toHaveTextContent("Djelatnost");
  });

  it("restores filters from a shared link, but never runs the ranking from it", async () => {
    renderApp(<GuidePage />, "/?djelatnost=office&korak=4&m2=120&cetvrti=00159,abc");
    expect(await screen.findByRole("heading", { name: /što vam je važno/i })).toBeInTheDocument();
    const s = useGuideStore.getState();
    expect(s.profile).toBe("office");
    expect(s.targetArea).toBe(120);
    expect(s.districtIds).toEqual(["00159"]);
    expect(s.step).toBe(2);
  });
});
