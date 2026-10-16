import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAnswer, ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * #1173: "Submit for review" with any blank answer shows a warning in place of
 * submitting, with the blank count per pillar, a button to each pillar that
 * has one, and "Submit anyway". A complete assessment submits straight
 * through. ZT's existing gate (an answer in every pillar) is unchanged.
 *
 * Expected copy is quoted from the approval on #736 (6206818759 item 4), not
 * imported from the component's copy module.
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
  return within(group).getByRole("radio", {
    name: new RegExp(`^S${stage}(?![0-9])`),
  });
}

describe("ZtSelfAssessment: blank answers before submit (#1173)", () => {
  it("warns in place of submitting, with the blank count", async () => {
    await mountWith(assessment(ONE_BLANK));
    expect(
      screen.getByText(
        "1 of 4 capabilities have no answer yet. Blank answers are left out of your results. Answer them now, or submit anyway.",
      ),
    ).toBeVisible();
    expect(ztClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("offers a button to each pillar with a blank, and none to a complete one", async () => {
    await mountWith(assessment(ONE_BLANK));
    expect(
      screen.getByRole("button", { name: "Go to Devices (1 blank)" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /^Go to Identity/ }),
    ).toBeNull();
  });

  it("goes to the pillar and scrolls it into view", async () => {
    await mountWith(assessment(ONE_BLANK));
    expect(screen.getByText("Pillar 1 of 2")).toBeVisible();
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Go to Devices (1 blank)" }),
      );
    });
    expect(screen.getByText("Pillar 2 of 2")).toBeVisible();
    expect(
      screen.getByRole("radiogroup", { name: "Maturity stage for CISA.DV.02" }),
    ).toBeVisible();
    expect(scrollIntoView).toHaveBeenCalled();
    expect(ztClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("submits on Submit anyway", async () => {
    await mountWith(assessment(ONE_BLANK));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Submit anyway" }));
    });
    expect(ztClient.submitSelfAssessment).toHaveBeenCalledTimes(1);
    expect(ztClient.submitSelfAssessment).toHaveBeenCalledWith("s1", {
      target_stage: 3,
    });
  });

  it("keeps Submit anyway off while an answer save is out (#758)", async () => {
    let release: (a: ZtAnswer) => void = () => undefined;
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockImplementation(
      () =>
        new Promise<ZtAnswer>((resolve) => {
          release = resolve;
        }),
    );
    await mountWith(assessment(ONE_BLANK));
    expect(screen.getByRole("button", { name: "Submit anyway" })).toBeEnabled();
    await act(async () => {
      fireEvent.blur(screen.getByLabelText("Notes for CISA.ID.01"), {
        target: { value: "a note" },
      });
    });
    expect(
      screen.getByRole("button", { name: "Submit anyway" }),
    ).toBeDisabled();
    await act(async () => {
      release({ ...answer("ans0", "CISA.ID.01", 2), notes: "a note" });
    });
    expect(screen.getByRole("button", { name: "Submit anyway" })).toBeEnabled();
    expect(ztClient.submitSelfAssessment).not.toHaveBeenCalled();
  });

  it("drops the warning once the blanks are answered, does not bring it back unasked, and then submits straight through", async () => {
    vi.mocked(ztClient.patchSelfAssessmentAnswer).mockImplementation(
      async (answerId, patch) =>
        ({ ...answer(answerId, "CISA.DV.02", null), ...patch }) as ZtAnswer,
    );
    await mountWith(assessment(ONE_BLANK));
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Go to Devices (1 blank)" }),
      );
    });
    await act(async () => {
      fireEvent.click(stageRadio("CISA.DV.02", 2));
    });
    expect(screen.queryByRole("button", { name: "Submit anyway" })).toBeNull();

    // Clearing the answer makes a blank again, but nobody pressed Submit.
    await act(async () => {
      fireEvent.click(stageRadio("CISA.DV.02", 2));
    });
    expect(stageRadio("CISA.DV.02", 2)).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.queryByText(/have no answer yet/)).toBeNull();

    await act(async () => {
      fireEvent.click(stageRadio("CISA.DV.02", 3));
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "Submit for review" }),
      );
    });
    expect(ztClient.submitSelfAssessment).toHaveBeenCalledTimes(1);
  });

  it("submits a complete assessment straight through, with no warning", async () => {
    await mountWith(assessment({ ...ONE_BLANK, "CISA.DV.02": 4 }));
    expect(ztClient.submitSelfAssessment).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/have no answer yet/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit anyway" })).toBeNull();
  });
});
