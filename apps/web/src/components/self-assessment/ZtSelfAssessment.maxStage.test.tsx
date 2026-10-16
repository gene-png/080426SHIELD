import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAnswer, ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * #922 on the client's own page: a stage above the capability's maximum is
 * unavailable, so the client never meets the API's refusal. (A synthetic
 * maximum of 3 on a CISA row stands in for a DoD capability with no Advanced
 * activity; the picker reads only the number.)
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

function cap(code: string, pillar: string, max_stage = 4) {
  return {
    code,
    pillar_code: pillar,
    name: `Name ${code}`,
    outcome: `Outcome ${code}`,
    max_stage,
  };
}

const CATALOG: ZtCatalog = {
  framework: "cisa_ztmm_2_0",
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "Who is asking.",
      capabilities: [cap("CISA.ID.01", "ID", 3), cap("CISA.ID.02", "ID")],
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

describe("ZtSelfAssessment #922", () => {
  it("makes the stage above a capability's maximum unavailable", async () => {
    vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(
      assessment({ "CISA.ID.01": null, "CISA.ID.02": null }),
    );
    render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
    const capped = await screen.findByRole("radiogroup", {
      name: "Maturity stage for CISA.ID.01",
    });
    const open = screen.getByRole("radiogroup", {
      name: "Maturity stage for CISA.ID.02",
    });
    expect(
      within(open).getByRole("radio", { name: "Optimal" }),
    ).not.toHaveAttribute("aria-disabled");
    expect(
      within(capped).getByRole("radio", { name: "Optimal" }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(
      within(capped).getByRole("radio", { name: "Advanced" }),
    ).not.toHaveAttribute("aria-disabled");
  });
});
