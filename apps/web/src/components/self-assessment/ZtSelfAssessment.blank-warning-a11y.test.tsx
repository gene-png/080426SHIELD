import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAnswer, ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * #1191 items 3 and 4: the blank-answer warning has an accessible name (its
 * message), takes focus when it appears, and "Go to" moves focus into the
 * pillar it opens. When "Submit anyway" is off because a pillar has no answer,
 * the warning says why, with the sentence the Submit button's title already
 * carries.
 *
 * Expected copy is quoted from the approvals on #736 (6206818759 item 4,
 * 6216024281) and from the existing Submit title, not imported from the
 * component's copy module.
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

function cap(code: string, pillar: string) {
  return {
    code,
    pillar_code: pillar,
    name: `Name ${code}`,
    outcome: `Outcome ${code}`,
  };
}

const CATALOG: ZtCatalog = {
  framework: "cisa_ztmm_2_0",
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "Who is asking.",
      capabilities: [cap("CISA.ID.01", "ID"), cap("CISA.ID.02", "ID")],
    },
    {
      code: "DV",
      name: "Devices",
      purpose: "What is asking.",
      capabilities: [cap("CISA.DV.01", "DV"), cap("CISA.DV.02", "DV")],
    },
  ],
  stages: [
    { stage: 1, label: "Traditional", description: "" },
    { stage: 2, label: "Initial", description: "" },
    { stage: 3, label: "Advanced", description: "" },
    { stage: 4, label: "Optimal", description: "" },
  ],
  total_capabilities: 4,
};

function answer(id: string, code: string, stage: number | null): ZtAnswer {
  return {
    id,
    assessment_id: "a1",
    capability_code: code,
    maturity_stage: stage,
    target_stage: null,
    notes: null,
    evidence_artifact_id: null,
    locked: false,
    answered_by: null,
    answered_at: null,
  } as ZtAnswer;
}

function assessment(
  stages: Record<string, number | null>,
  status = "draft",
): ZtAssessment {
  return {
    id: "a1",
    service_id: "s1",
    framework: "cisa_ztmm_2_0",
    version: 1,
    status,
    approved_at: null,
    approved_by: null,
    answers: Object.entries(stages).map(([code, stage], i) =>
      answer(`ans${i}`, code, stage),
    ),
    client_target_stage: 3,
  } as ZtAssessment;
}

const scrollIntoView = vi.fn();

beforeEach(() => {
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
  vi.mocked(ztClient.patchSelfAssessmentAnswer).mockReset();
  vi.mocked(ztClient.submitSelfAssessment).mockReset();
  vi.mocked(ztClient.submitSelfAssessment).mockResolvedValue(
    assessment({}, "submitted"),
  );
});

afterEach(() => {
  vi.mocked(ztClient.fetchSelfAssessment).mockReset();
});

async function mountWith(a: ZtAssessment): Promise<void> {
  vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(a);
  render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
  const submit = await screen.findByRole("button", {
    name: "Submit for review",
  });
  await act(async () => {
    fireEvent.click(submit);
  });
}

// Every pillar started, so Submit is enabled; one blank in DV.
const ONE_BLANK = {
  "CISA.ID.01": 2,
  "CISA.ID.02": 3,
  "CISA.DV.01": 1,
  "CISA.DV.02": null,
};

function stageRadio(code: string, stage: number): HTMLElement {
  const group = screen.getByRole("radiogroup", {
    name: `Maturity stage for ${code}`,
  });
  // Z3 (#736 6205956728): a stage button is named by its stage's name alone.
  const label = CATALOG.stages.find((s) => s.stage === stage)?.label;
  if (label === undefined) throw new Error(`no stage ${stage} in CATALOG`);
  return within(group).getByRole("radio", { name: label });
}

const MESSAGE =
  "1 of 4 capabilities have no answer yet. Your consultant may score them, but any left blank are reported as not scored. Answer them now, or submit anyway.";
const PILLAR_REASON = "Answer at least one capability in every pillar first.";

describe("ZtSelfAssessment: the blank-answer warning, focus and reasons (#1191)", () => {
  it("is named by its message and takes focus when it appears", async () => {
    await mountWith(assessment(ONE_BLANK));
    const warning = screen.getByRole("status", { name: MESSAGE });
    expect(warning).toHaveFocus();
  });

  it("focuses the pillar only once it is named for the pillar chosen", async () => {
    // Focus lands on the one section the page reuses for every pillar; if it
    // landed before the render, a screen reader would hear the OLD pillar.
    const nameAtFocus: Array<string | null> = [];
    const onFocusIn = (e: FocusEvent): void => {
      if (e.target instanceof HTMLElement && e.target.tagName === "SECTION") {
        nameAtFocus.push(e.target.getAttribute("aria-label"));
      }
    };
    document.addEventListener("focusin", onFocusIn);
    try {
      await mountWith(assessment(ONE_BLANK));
      await act(async () => {
        fireEvent.click(
          screen.getByRole("button", { name: "Go to Devices (1 blank)" }),
        );
      });
    } finally {
      document.removeEventListener("focusin", onFocusIn);
    }
    expect(nameAtFocus).toEqual(["DV Devices"]);
  });

  it("moves focus into the pillar on Go to", async () => {
    await mountWith(assessment(ONE_BLANK));
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Go to Devices (1 blank)" }),
      );
    });
    expect(screen.getByRole("region", { name: "DV Devices" })).toHaveFocus();
  });

  it("says why Submit anyway is off when a pillar has lost every answer", async () => {
    // Each answer comes back under its OWN capability code, as the API sends it.
    const codeOf = (answerId: string): string => {
      const found = assessment(ONE_BLANK).answers.find((a) => a.id === answerId);
      if (!found) throw new Error(`no answer ${answerId} in the fixture`);
      return found.capability_code;
    };
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockImplementation(
      async (answerId, patch) =>
        ({ ...answer(answerId, codeOf(answerId), null), ...patch }) as ZtAnswer,
    );
    await mountWith(assessment(ONE_BLANK));
    expect(screen.queryByText(PILLAR_REASON)).toBeNull();
    // Identity is the open pillar; clear both of its answers.
    await act(async () => {
      fireEvent.click(stageRadio("CISA.ID.01", 2));
    });
    await act(async () => {
      fireEvent.click(stageRadio("CISA.ID.02", 3));
    });
    const anyway = screen.getByRole("button", { name: "Submit anyway" });
    expect(anyway).toBeDisabled();
    const warning = screen.getByRole("status", { name: /have no answer yet/ });
    const reason = within(warning).getByText(PILLAR_REASON);
    expect(reason).toBeVisible();
    expect(anyway).toHaveAccessibleDescription(PILLAR_REASON);
  });

  it("leaves focus alone on the stepper's Next (only the warning's Go to moves it)", async () => {
    await mountWith(assessment(ONE_BLANK));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^Next: Devices/ }));
    });
    const region = screen.getByRole("region", { name: "DV Devices" });
    expect(region).toBeVisible();
    expect(region).not.toHaveFocus();
  });

  it("gives no reason while Submit anyway is on", async () => {
    await mountWith(assessment(ONE_BLANK));
    const anyway = screen.getByRole("button", { name: "Submit anyway" });
    expect(anyway).toBeEnabled();
    expect(
      within(
        screen.getByRole("status", { name: /have no answer yet/ }),
      ).queryByText(PILLAR_REASON),
    ).toBeNull();
    expect(anyway).not.toHaveAccessibleDescription(PILLAR_REASON);
  });
});
