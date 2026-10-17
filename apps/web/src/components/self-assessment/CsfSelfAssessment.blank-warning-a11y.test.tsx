import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAnswer, CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #1191 items 3 and 4, the CSF half (the ZT half is
 * ZtSelfAssessment.blank-warning-a11y.test.tsx): the blank-answer warning has
 * an accessible name (its message), takes focus when it appears, and "Go to"
 * moves focus to the function it opens. When "Submit anyway" is off because a
 * function has no answer, the warning says why, with the sentence the Submit
 * button's title already carries.
 *
 * Expected copy is quoted from the approvals on #736 (6206818759 item 4,
 * 6216024281), not imported from the component's copy module.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

function sub(code: string, fn: string, minProfile = "LOW") {
  return {
    code,
    function: fn,
    category: code.slice(0, 5),
    name: `Name ${code}`,
    outcome: `Outcome ${code}`,
    min_profile: minProfile,
  };
}

// GV has three outcomes, one of them HIGH-only; ID has two, and ID.AM-02 is
// answered in every fixture, so every function has an answer and #1171's
// submit lock (an answer in every function) never holds Submit off here.
const CATALOG = {
  functions: [
    {
      code: "GV",
      name: "Govern",
      purpose: "Set direction.",
      categories: [
        {
          code: "GV.OC",
          function: "GV",
          name: "Organizational Context",
          purpose: "Know the mission.",
          subcategories: [
            sub("GV.OC-01", "GV"),
            sub("GV.OC-02", "GV"),
            sub("GV.OC-03", "GV", "HIGH"),
          ],
        },
      ],
    },
    {
      code: "ID",
      name: "Identify",
      purpose: "Know what you have.",
      categories: [
        {
          code: "ID.AM",
          function: "ID",
          name: "Asset Management",
          purpose: "Inventory.",
          subcategories: [sub("ID.AM-01", "ID"), sub("ID.AM-02", "ID")],
        },
      ],
    },
  ],
  tiers: [
    { tier: 1, short_label: "Partial", description: "" },
    { tier: 2, short_label: "Risk Informed", description: "" },
    { tier: 3, short_label: "Repeatable", description: "" },
    { tier: 4, short_label: "Adaptive", description: "" },
  ],
  total_subcategories: 5,
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

function assessment(
  tiers: Record<string, number | null>,
  opts: { status?: string; profile?: string | null } = {},
): CsfAssessment {
  return {
    id: "a1",
    service_id: "s1",
    version: 1,
    status: opts.status ?? "draft",
    approved_at: null,
    approved_by: null,
    answers: Object.entries(tiers).map(([code, tier], i) =>
      answer(`ans${i}`, code, tier),
    ),
    client_target_tier: 3,
    client_profile: opts.profile === undefined ? "MOD" : opts.profile,
  } as CsfAssessment;
}

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(csfClient.patchSelfAssessmentAnswer).mockReset();
  vi.mocked(csfClient.submitSelfAssessment).mockReset();
  vi.mocked(csfClient.submitSelfAssessment).mockResolvedValue(
    assessment({}, { status: "submitted" }),
  );
});

afterEach(() => {
  vi.mocked(csfClient.fetchSelfAssessment).mockReset();
});

async function mountWith(a: CsfAssessment): Promise<void> {
  vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(a);
  render(<CsfSelfAssessment serviceId="s1" />);
  const submit = await screen.findByRole("button", {
    name: "Submit for review",
  });
  await act(async () => {
    fireEvent.click(submit);
  });
}

// One in-scope blank, in ID (GV.OC-03 is out of scope at MOD).
const ONE_BLANK = {
  "GV.OC-01": 2,
  "GV.OC-02": 3,
  "GV.OC-03": null,
  "ID.AM-01": null,
  "ID.AM-02": 2,
};

function tierRadio(code: string, tier: number): HTMLElement {
  const group = screen.getByRole("radiogroup", {
    name: `Maturity tier for ${code}`,
  });
  return within(group).getByRole("radio", {
    name: new RegExp(`^T${tier}(?![0-9])`),
  });
}

const MESSAGE =
  "1 of 4 outcomes have no answer yet. Your consultant may score them, but any left blank are reported as not scored. Answer them now, or submit anyway.";
const FUNCTION_REASON = "Answer at least one outcome in every function first.";

describe("CsfSelfAssessment: the blank-answer warning, focus and reasons (#1191)", () => {
  it("is named by its message and takes focus when it appears", async () => {
    await mountWith(assessment(ONE_BLANK));
    expect(screen.getByRole("status", { name: MESSAGE })).toHaveFocus();
  });

  it("moves focus to the function's tab on Go to", async () => {
    await mountWith(assessment(ONE_BLANK));
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Go to Identify (1 blank)" }),
      );
    });
    const tab = screen.getByRole("tab", { name: /^ID/ });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(tab).toHaveFocus();
  });

  it("says why Submit anyway is off when a function has lost every answer", async () => {
    vi.mocked(csfClient.patchSelfAssessmentAnswer).mockImplementation(
      async (answerId, patch) =>
        ({ ...answer(answerId, "GV.OC-01", null), ...patch }) as CsfAnswer,
    );
    await mountWith(assessment(ONE_BLANK));
    expect(screen.queryByText(FUNCTION_REASON)).toBeNull();
    // Govern is the open function; clear GV.OC-01 and GV.OC-02.
    await act(async () => {
      fireEvent.click(tierRadio("GV.OC-01", 2));
    });
    await act(async () => {
      fireEvent.click(tierRadio("GV.OC-02", 3));
    });
    const anyway = screen.getByRole("button", { name: "Submit anyway" });
    expect(anyway).toBeDisabled();
    const warning = screen.getByRole("status", { name: /have no answer yet/ });
    expect(within(warning).getByText(FUNCTION_REASON)).toBeVisible();
    expect(anyway).toHaveAccessibleDescription(FUNCTION_REASON);
  });

  it("gives no reason while Submit anyway is on", async () => {
    await mountWith(assessment(ONE_BLANK));
    const anyway = screen.getByRole("button", { name: "Submit anyway" });
    expect(anyway).toBeEnabled();
    expect(
      within(
        screen.getByRole("status", { name: /have no answer yet/ }),
      ).queryByText(FUNCTION_REASON),
    ).toBeNull();
    expect(anyway).not.toHaveAccessibleDescription(FUNCTION_REASON);
  });
});
