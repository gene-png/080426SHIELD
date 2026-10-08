import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as ztClient from "@/lib/zt/client";
import type { ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtSelfAssessment } from "./ZtSelfAssessment";

/**
 * #838: the client's own self-assessment page discloses answers migration
 * 0063 kept on rows CISA ZTMM 2.0 does not have, as the consultant's workspace
 * and the exports do. The page reads the same `GET .../self-assessment`
 * response (`ZtAssessmentResponse`), so the sentence is the API's own,
 * written here exactly as `zt/retired.py` builds it for one answer, and
 * rendered as given. Without it the field reaches the browser and is
 * discarded there (the #322 shape).
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

const ONE =
  "1 recorded answer belongs to a row that CISA ZTMM 2.0 does not have, so it is not scored.";

const CATALOG: ZtCatalog = {
  framework: "cisa_ztmm_2_0",
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "Who is asking.",
      capabilities: [
        {
          code: "CISA.ID.01",
          pillar_code: "ID",
          name: "Authentication",
          outcome: "CISA Optimal: x",
        },
      ],
    },
  ],
  stages: [
    { stage: 1, label: "Traditional", description: "" },
    { stage: 2, label: "Initial", description: "" },
    { stage: 3, label: "Advanced", description: "" },
    { stage: 4, label: "Optimal", description: "" },
  ],
  total_capabilities: 1,
};

function assessment(note: string | null, count: number): ZtAssessment {
  return {
    id: "a1",
    service_id: "s1",
    framework: "cisa_ztmm_2_0",
    version: 1,
    status: "draft",
    approved_at: null,
    approved_by: null,
    answers: [
      {
        id: "ans1",
        assessment_id: "a1",
        capability_code: "CISA.ID.01",
        maturity_stage: 2,
        target_stage: null,
        notes: null,
        evidence_artifact_id: null,
        locked: false,
        answered_by: null,
        answered_at: null,
      },
    ],
    client_target_stage: 3,
    retired_answers: count,
    retired_answers_note: note,
  } as ZtAssessment;
}

describe("ZtSelfAssessment discloses answers on rows CISA does not have (#838)", () => {
  it("shows the API's sentence", async () => {
    vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
    vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(
      assessment(ONE, 1),
    );
    render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
    expect(await screen.findByTestId("zt-retired-answers")).toHaveTextContent(
      ONE,
    );
  });

  it("shows nothing when there is nothing to disclose", async () => {
    vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CATALOG);
    vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue(
      assessment(null, 0),
    );
    render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
    // What must appear, before what must not: the page has loaded.
    await screen.findByLabelText("Notes for CISA.ID.01");
    expect(screen.queryByTestId("zt-retired-answers")).toBeNull();
  });
});
