import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockApi, PROFILES, renderApp } from "@/test/utils";

import { GuidePage } from "./GuidePage";
import { INITIAL, useGuideStore } from "./store";

const BRIEF = {
  suggestion: {
    suggested_profile: null,
    status: "unsupported",
    requires_confirmation: true,
    candidates: [
      { profile: "workshop", similarity: 0.55, matched_example: "Servis kućanskih aparata." },
      { profile: "retail", similarity: 0.52, matched_example: "Trgovina mješovitom robom." },
    ],
    min_similarity: 0.34,
    min_margin: 0.14,
    method: "maximum_cosine_over_profile_examples",
    model_id: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    model_revision: "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    config_sha256: "0".repeat(64),
  },
  area_m2: null,
  budget_eur: null,
  districts: [],
  priorities: [],
  notices: [],
};

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

  it("suggests a profile from free text but lets the user choose", async () => {
    mockApi({
      "/api/v1/profiles": PROFILES,
      "/api/v1/business-brief": BRIEF,
    });
    renderApp(<GuidePage />);
    await screen.findAllByRole("radio");
    const submit = screen.getByRole("button", { name: /predloži djelatnost/i });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/opišite djelatnost/i), {
      target: { value: "Autopraonica" },
    });
    fireEvent.click(submit);
    expect(await screen.findByText(/nismo sigurni/i)).toBeInTheDocument();
    expect(screen.getByText(/sličnost 0,55/)).toBeInTheDocument();
    expect(useGuideStore.getState().profile).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /odaberi radionica/i }));
    expect(useGuideStore.getState().profile).toBe("workshop");
  });

  it("applies proposals from the description only when the user chooses a profile", async () => {
    mockApi({
      "/api/v1/profiles": PROFILES,
      "/api/v1/business-brief": {
        ...BRIEF,
        area_m2: 45,
        budget_eur: 800,
        districts: [{ district_id: "00680", name: "Trnje", words: "trnju" }],
        priorities: [
          { criterion: "universities", level: 3, words: "studente" },
          { criterion: "parking", level: 0, words: "parking" },
        ],
      },
    });
    renderApp(<GuidePage />);
    await screen.findAllByRole("radio");
    fireEvent.change(screen.getByLabelText(/opišite djelatnost/i), {
      target: { value: "Radionica u Trnju za studente, parking nije bitan" },
    });
    fireEvent.click(screen.getByRole("button", { name: /predloži djelatnost/i }));

    expect(await screen.findByText(/jer ste napisali „studente”/)).toBeInTheDocument();
    expect(screen.getByText(/ciljna površina 45 m²/i)).toBeInTheDocument();
    expect(useGuideStore.getState().targetArea).toBeNull();
    expect(useGuideStore.getState().districtIds).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: /odaberi radionica/i }));
    const s = useGuideStore.getState();
    expect(s.profile).toBe("workshop");
    expect(s.targetArea).toBe(45);
    expect(s.budget).toBe(800);
    expect(s.districtIds).toEqual(["00680"]);
    expect(s.levels?.universities).toBe(3);
    expect(s.levels?.parking).toBe(0);
    expect(s.briefWords.universities).toBe("studente");

    useGuideStore.getState().resetLevels();
    expect(useGuideStore.getState().levels).toBeNull();
    expect(useGuideStore.getState().briefWords).toEqual({});
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
