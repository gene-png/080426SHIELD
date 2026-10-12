import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AiResultCard } from "./AiResultCard";

describe("AiResultCard (for #1087)", () => {
  it("leads with the outcome: the card's text starts with it", () => {
    render(
      <AiResultCard tone="warning" outcome="40 of 45 rows scored">
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const card = screen.getByTestId("ai-result-card");
    expect(card.textContent?.startsWith("40 of 45 rows scored")).toBe(true);
    expect(card.textContent).toBe("40 of 45 rows scoredDETAIL");
  });

  it("puts the outcome before the detail in the document", () => {
    render(
      <AiResultCard tone="success" outcome="OUTCOME">
        <p>DETAIL</p>
      </AiResultCard>,
    );
    const outcome = screen.getByText("OUTCOME");
    const detail = screen.getByText("DETAIL");
    expect(
      outcome.compareDocumentPosition(detail) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("adds no heading or tone words of its own (none is approved)", () => {
    const tones = ["success", "warning", "failure"] as const;
    const classes = tones.map((tone) => {
      const { unmount } = render(<AiResultCard tone={tone} outcome="X" />);
      const card = screen.getByTestId("ai-result-card");
      expect(card.textContent).toBe("X");
      const cls = card.className;
      unmount();
      return cls;
    });
    // Tone is colour only, and each tone looks different.
    expect(new Set(classes).size).toBe(tones.length);
  });
});
