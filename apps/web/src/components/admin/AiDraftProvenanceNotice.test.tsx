import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AiDraftProvenanceNotice } from "./AiDraftProvenanceNotice";

describe("AiDraftProvenanceNotice (#68)", () => {
  it("names both halves of the provenance: model-produced AND client-informed", () => {
    // The whole point of the control. Saying only "AI-drafted" would leave the
    // actual confusion in place — that some of this text traces back to
    // client-submitted input — which is the thing nothing on the page marked.
    const { container } = render(<AiDraftProvenanceNotice />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/AI-drafted/);
    expect(text).toMatch(/produced by the model/);
    expect(text).toMatch(/informed by client-submitted input/);
  });

  it("tells the consultant what to DO with it", () => {
    // A provenance label that does not say what follows from it is decoration.
    const { container } = render(<AiDraftProvenanceNotice />);
    expect(container.textContent).toMatch(/draft to verify, not as findings/);
  });

  it("is not dismissable — no control of any kind", () => {
    // A notice a consultant can turn off is one they turn off on day two, and
    // the risk it describes is present on every run.
    const { container } = render(<AiDraftProvenanceNotice />);
    expect(container.querySelector("button")).toBeNull();
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("adds no live region and no role — #69 is already open on announcements", () => {
    // Another announced region here would make the panel's announcement story
    // worse, not better. This is static informational copy.
    const { container } = render(<AiDraftProvenanceNotice />);
    const el = container.firstElementChild;
    expect(el).not.toBeNull();
    expect(el?.getAttribute("role")).toBeNull();
    expect(el?.getAttribute("aria-live")).toBeNull();
    expect(container.querySelector("[aria-live]")).toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});
