import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAnswer, CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #1171, review of 1f252d9f: "Submit anyway" honours Gene's lock too. Open the
 * blank-answer warning while every function has an answer, then clear a
 * function's only answer: the warning stays up, and its button is the only
 * way left to submit, so it must be off while that function has no answer.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

function sub(code: string, fn: string) {
  return {
    code,
    function: fn,
    category: code.slice(0, 5),
    name: `Name ${code}`,
    outcome: `Outcome ${code}`,
    min_profile: "LOW",
  };
}

function fn(code: string, name: string, subs: string[]) {
  return {
    code,
    name,
    purpose: `Purpose ${code}`,
    categories: [
      {
        code: `${code}.XX`,
        function: code,
        name: `Category ${code}`,
        purpose: "",
        subcategories: subs.map((s) => sub(s, code)),
      },
    ],
  };
}

const CATALOG = {
  functions: [
    fn("GV", "Govern", ["GV.OC-01", "GV.OC-02"]),
    fn("ID", "Identify", ["ID.AM-01"]),
  ],
  tiers: [
    { tier: 1, short_label: "Partial", description: "" },
    { tier: 2, short_label: "Risk Informed", description: "" },
    { tier: 3, short_label: "Repeatable", description: "" },
    { tier: 4, short_label: "Adaptive", description: "" },
  ],
  total_subcategories: 3,
} as unknown as CsfCatalog;

function answer(id: string, code: string, tier: number | null): CsfAnswer {
  return {
    id,
    assessment_id: "a1",
    subcategory_code: code,
    maturity_tier: tier,
    notes: null,
    evidence_artifact_id: null,
    answered_by: null,
    answered_at: null,
  };
}

// Both functions have an answer and GV.OC-02 is blank, so Submit is open and
// pressing it shows the warning.
const ASSESSMENT = {
  id: "a1",
  service_id: "s1",
  version: 1,
  status: "draft",
  approved_at: null,
  approved_by: null,
  answers: [
    answer("a0", "GV.OC-01", 2),
    answer("a1", "GV.OC-02", null),
    answer("a2", "ID.AM-01", 2),
  ],
  client_target_tier: 3,
  client_profile: null,
} as unknown as CsfAssessment;

function tierRadio(code: string, tier: number): HTMLElement {
  const group = screen.getByRole("radiogroup", {
    name: `Maturity tier for ${code}`,
  });
  return within(group).getByRole("radio", {
    name: new RegExp(`^T${tier}(?![0-9])`),
  });
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(ASSESSMENT);
  vi.mocked(csfClient.submitSelfAssessment).mockReset();
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockReset();
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockImplementation(
    async (answerId, patch) =>
      ({ ...answer(answerId, "ID.AM-01", null), ...patch }) as CsfAnswer,
  );
});

describe("CsfSelfAssessment: the warning's Submit anyway honours the lock (#1171)", () => {
  it("turns Submit anyway off when a function loses its only answer with the warning open", async () => {
    render(<CsfSelfAssessment serviceId="s1" />);
    await act(async () => {
      fireEvent.click(
        await screen.findByRole("button", { name: "Submit for review" }),
      );
    });
    const anyway = screen.getByRole("button", { name: "Submit anyway" });
    // The precondition: open while every function has an answer.
    expect(anyway).toBeEnabled();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next: Identify →" }));
    });
    // Clicking the checked tier clears ID's only answer; the save settles.
    await act(async () => {
      fireEvent.click(tierRadio("ID.AM-01", 2));
    });
    expect(tierRadio("ID.AM-01", 2)).toHaveAttribute("aria-checked", "false");
    expect(csfClient.patchSelfAssessmentAnswer).toHaveBeenCalledTimes(1);

    const stillThere = screen.getByRole("button", { name: "Submit anyway" });
    expect(stillThere).toBeDisabled();
    await act(async () => {
      fireEvent.click(stillThere);
    });
    expect(csfClient.submitSelfAssessment).not.toHaveBeenCalled();
  });
});
