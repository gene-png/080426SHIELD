import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAnswer, CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #1171: the CSF self-assessment steps through its functions the way the ZT
 * one steps through pillars: "Function i of n", per-function progress,
 * Previous / Next, and Next scrolls to the top of the questionnaire.
 *
 * Copy quoted from the advisor's approval on #736 (6207611148), which names
 * functions rather than codes. Gene decided Submit stays locked until every
 * function has at least one answer, as ZT's does. The lock's sentence (L1)
 * and the locked button's title (L2) are approved verbatim on #736
 * (6216024281), and so is leaving Submit open when no function is in scope.
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
    fn("PR", "Protect", ["PR.AA-01"]),
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
    answer("a2", "ID.AM-01", null),
    answer("a3", "PR.AA-01", 3),
  ],
  client_target_tier: 3,
  client_profile: null,
} as unknown as CsfAssessment;

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(ASSESSMENT);
});

async function mount(): Promise<void> {
  render(<CsfSelfAssessment serviceId="s1" />);
  await screen.findByRole("button", { name: "Submit for review" });
}

function selectedTab(): HTMLElement {
  return screen.getByRole("tab", { selected: true });
}

describe("CsfSelfAssessment steps through its functions (#1171)", () => {
  it("keeps Submit off until every function has an answer, and says which still need one", async () => {
    // ID has no answer yet.
    await mount();
    const submit = screen.getByRole("button", { name: "Submit for review" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAttribute(
      "title",
      "Answer at least one outcome in every function first.",
    );
    expect(
      screen.getByText(
        "Add at least one answer to every function before submitting. Still needs attention: Identify.",
      ),
    ).toBeVisible();
  });

  it("leaves Submit open when no function is in scope", async () => {
    vi.mocked(csfClient.fetchCatalog).mockResolvedValue({
      ...CATALOG,
      functions: [],
      total_subcategories: 0,
    } as unknown as CsfCatalog);
    vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue({
      ...ASSESSMENT,
      answers: [],
    });
    await mount();
    const submit = screen.getByRole("button", { name: "Submit for review" });
    expect(submit).toBeEnabled();
    expect(submit).not.toHaveAttribute("title");
    expect(screen.queryByText(/Still needs attention/)).toBeNull();
  });

  it("lets Submit through once every function has an answer", async () => {
    vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue({
      ...ASSESSMENT,
      answers: ASSESSMENT.answers.map((a) =>
        a.subcategory_code === "ID.AM-01" ? { ...a, maturity_tier: 1 } : a,
      ),
    });
    await mount();
    const submit = screen.getByRole("button", { name: "Submit for review" });
    expect(submit).toBeEnabled();
    expect(submit).not.toHaveAttribute("title");
    expect(screen.queryByText(/Still needs attention/)).toBeNull();
  });

  it("says how many functions there are and that every area needs an answer", async () => {
    await mount();
    expect(
      screen.getByText(
        "This assessment covers 3 functions. Step through each one and rate every outcome for where your organization stands today. Each function needs at least one answer before you can submit. Use Previous and Next to move between them.",
      ),
    ).toBeVisible();
  });

  it("starts on the first function, with Previous off, and shows its progress", async () => {
    await mount();
    expect(screen.getByText("Function 1 of 3")).toBeVisible();
    expect(selectedTab()).toHaveTextContent(/^GV/);
    expect(screen.getByRole("button", { name: "← Previous" })).toBeDisabled();
    expect(screen.getByText("Govern: 1 of 2 answered")).toBeVisible();
  });

  it("Next goes to the next function and scrolls to the top of the questionnaire", async () => {
    await mount();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next: Identify →" }));
    });
    expect(selectedTab()).toHaveTextContent(/^ID/);
    expect(screen.getByText("Function 2 of 3")).toBeVisible();
    expect(screen.getByText("Identify: 0 of 1 answered")).toBeVisible();
    expect(screen.getByLabelText("Maturity tier for ID.AM-01")).toBeVisible();
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("Previous goes back, and also scrolls", async () => {
    await mount();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Next: Identify →" }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "← Previous" }));
    });
    expect(selectedTab()).toHaveTextContent(/^GV/);
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });

  it("on the last function, offers no Next and says to review, then submit", async () => {
    await mount();
    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /^PR/ }));
    });
    expect(screen.getByText("Function 3 of 3")).toBeVisible();
    expect(screen.queryByRole("button", { name: /^Next:/ })).toBeNull();
    expect(
      screen.getByText("Last function. Review the others, then submit below."),
    ).toBeVisible();
  });

  it("follows a tab click: the counter and Next track the tab the client picked", async () => {
    await mount();
    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /^ID/ }));
    });
    expect(screen.getByText("Function 2 of 3")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Next: Protect →" }),
    ).toBeInTheDocument();
  });
});
