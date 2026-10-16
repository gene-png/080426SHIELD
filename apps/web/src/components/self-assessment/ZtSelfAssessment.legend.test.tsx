import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAnswer, ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * Z2 and Z1 on the client's own page (#736 6204461502 section 6, approved at
 * 6205956728): the legend is "The highlighted stage is your current answer.",
 * once; the admin legend and the admin-only Z1 ("Self-reported, not
 * validated") never appear here. Literals quoted from the approval.
 */

const Z2_CLIENT = "The highlighted stage is your current answer.";
const Z2_ADMIN = "The highlighted stage is the current assessed score.";
const Z1 = "Self-reported, not validated";

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

beforeEach(() => {
  vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
});

describe("ZtSelfAssessment Z2: the client's legend", () => {
  it("shows the client legend once, and no admin copy", async () => {
    // A stage with blank notes: the state Z1 would flag on the admin page.
    vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(
      assessment({ "CISA.ID.01": 2, "CISA.ID.02": null }),
    );
    render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
    // The positive state first.
    expect(await screen.findAllByText(Z2_CLIENT)).toHaveLength(1);
    // Z2 sits UNDER the stage buttons: after the last stage picker.
    const groups = screen.getAllByRole("radiogroup");
    expect(
      groups[groups.length - 1].compareDocumentPosition(
        screen.getByText(Z2_CLIENT),
      ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByText(Z2_ADMIN)).toBeNull();
    expect(screen.queryByText(Z1)).toBeNull();
  });
});
