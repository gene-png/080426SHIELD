import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAnswer, CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #1173: "Submit for review" with any blank answer shows a warning in place of
 * submitting, with the blank count per function, a button to each function
 * that has one, and "Submit anyway". A complete assessment submits straight
 * through.
 *
 * Expected copy is quoted from the approval on #736 (6206818759 item 4), not
 * imported from the component's copy module.
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

// GV has three outcomes, one of them HIGH-only; ID has one.
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
          subcategories: [sub("ID.AM-01", "ID")],
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
  total_subcategories: 4,
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

// At the MOD profile GV.OC-03 is out of scope, so in scope are GV.OC-01,
// GV.OC-02 and ID.AM-01. One GV blank and the ID blank.
const TWO_BLANK = {
  "GV.OC-01": 2,
  "GV.OC-02": null,
  "GV.OC-03": null,
  "ID.AM-01": null,
};

// One in-scope blank, in ID (GV.OC-03 is out of scope at MOD).
const ONE_BLANK = {
  "GV.OC-01": 2,
  "GV.OC-02": 3,
  "GV.OC-03": null,
  "ID.AM-01": null,
};

function tierRadio(code: string, tier: number): HTMLElement {
  const group = screen.getByRole("radiogroup", {
    name: `Maturity tier for ${code}`,
  });
  return within(group).getByRole("radio", {
    name: new RegExp(`^T${tier}(?![0-9])`),
  });
}

describe("CsfSelfAssessment: blank answers before submit (#1173)", () => {
  it("warns in place of submitting, with the in-scope blank count", async () => {
    await mountWith(assessment(TWO_BLANK));
    expect(
      screen.getByText(
        "2 of 3 outcomes have no answer yet. Your consultant may score them, but any left blank are reported as not scored. Answer them now, or submit anyway.",
      ),
    ).toBeVisible();
    expect(csfClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("offers a button to each function with a blank, and none to a complete one", async () => {
    await mountWith(
      assessment({
        "GV.OC-01": 2,
        "GV.OC-02": 3,
        "GV.OC-03": null,
        "ID.AM-01": null,
      }),
    );
    expect(
      screen.getByRole("button", { name: "Go to Identify (1 blank)" }),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: /^Go to Govern/ })).toBeNull();
  });

  it("goes to the function: selects its tab and scrolls the questionnaire into view", async () => {
    await mountWith(assessment(TWO_BLANK));
    expect(screen.getByRole("tab", { name: /^GV/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Go to Identify (1 blank)" }),
      );
    });
    expect(screen.getByRole("tab", { name: /^ID/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByLabelText("Maturity tier for ID.AM-01")).toBeVisible();
    expect(scrollIntoView).toHaveBeenCalled();
    expect(csfClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("submits on Submit anyway", async () => {
    await mountWith(assessment(TWO_BLANK));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit anyway" }));
    });
    expect(csfClient.submitSelfAssessment).toHaveBeenCalledTimes(1);
    expect(csfClient.submitSelfAssessment).toHaveBeenCalledWith("s1", {
      target_tier: 3,
    });
  });

  it("keeps Submit anyway off while an answer save is out (#758)", async () => {
    let release: (a: CsfAnswer) => void = () => undefined;
    vi.mocked(csfClient.patchSelfAssessmentAnswer).mockImplementation(
      () =>
        new Promise<CsfAnswer>((resolve) => {
          release = resolve;
        }),
    );
    await mountWith(assessment(TWO_BLANK));
    expect(screen.getByRole("button", { name: "Submit anyway" })).toBeEnabled();
    await act(async () => {
      fireEvent.blur(screen.getByLabelText("Notes for GV.OC-01"), {
        target: { value: "a note" },
      });
    });
    expect(
      screen.getByRole("button", { name: "Submit anyway" }),
    ).toBeDisabled();
    await act(async () => {
      release({ ...answer("ans0", "GV.OC-01", 2), notes: "a note" });
    });
    expect(screen.getByRole("button", { name: "Submit anyway" })).toBeEnabled();
    expect(csfClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("drops the warning once the blanks are answered, does not bring it back unasked, and then submits straight through", async () => {
    vi.mocked(csfClient.patchSelfAssessmentAnswer).mockImplementation(
      async (answerId, patch) =>
        ({ ...answer(answerId, "ID.AM-01", null), ...patch }) as CsfAnswer,
    );
    await mountWith(assessment(ONE_BLANK));
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Go to Identify (1 blank)" }),
      );
    });
    await act(async () => {
      fireEvent.click(tierRadio("ID.AM-01", 2));
    });
    expect(screen.queryByRole("button", { name: "Submit anyway" })).toBeNull();

    // Clearing the answer makes a blank again, but nobody pressed Submit.
    await act(async () => {
      fireEvent.click(tierRadio("ID.AM-01", 2));
    });
    expect(tierRadio("ID.AM-01", 2)).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByText(/have no answer yet/)).toBeNull();

    await act(async () => {
      fireEvent.click(tierRadio("ID.AM-01", 3));
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Submit for review" }),
      );
    });
    expect(csfClient.submitSelfAssessment).toHaveBeenCalledTimes(1);
  });

  it("submits a complete assessment straight through, with no warning", async () => {
    // GV.OC-03 is blank but out of scope at MOD, so this is complete.
    await mountWith(
      assessment({
        "GV.OC-01": 2,
        "GV.OC-02": 3,
        "GV.OC-03": null,
        "ID.AM-01": 1,
      }),
    );
    expect(csfClient.submitSelfAssessment).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/have no answer yet/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit anyway" })).toBeNull();
  });

  it("counts the HIGH-only outcome when the profile is HIGH", async () => {
    await mountWith(assessment(TWO_BLANK, { profile: "HIGH" }));
    expect(
      screen.getByText(
        "3 of 4 outcomes have no answer yet. Your consultant may score them, but any left blank are reported as not scored. Answer them now, or submit anyway.",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Go to Govern (2 blank)" }),
    ).toBeVisible();
  });
});
