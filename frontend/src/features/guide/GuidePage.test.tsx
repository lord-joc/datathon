import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { GuidePage } from "./GuidePage";
import { useGuideStore } from "./store";

describe("GuidePage", () => {
  beforeEach(() => {
    useGuideStore.setState({ step: 0, profile: null });
  });

  it("shows all seven profiles", () => {
    render(<GuidePage />);
    expect(screen.getAllByRole("radio")).toHaveLength(7);
  });

  it("blocks the next step until a profile is chosen", () => {
    render(<GuidePage />);
    const next = screen.getByRole("button", { name: /dalje/i });
    expect(next).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: /ured/i }));
    expect(next).toBeEnabled();

    fireEvent.click(next);
    expect(useGuideStore.getState().step).toBe(1);
  });

  it("marks the current step for assistive technology", () => {
    render(<GuidePage />);
    expect(screen.getByRole("button", { current: "step" })).toHaveTextContent("Djelatnost");
  });
});
