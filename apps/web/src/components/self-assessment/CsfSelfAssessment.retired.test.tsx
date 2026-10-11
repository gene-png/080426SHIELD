import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAssessment, CsfCatalog } from "@/lib/csf/types";

import { CsfSelfAssessment } from "./CsfSelfAssessment";

/**
 * #852 on the client's self-assessment. An answer kept on ID.AM-09 (a
 * subcategory NIST CSF 2.0 does not have) is not in the questionnaire, which
 * iterates the catalog, and the API sends the approved sentence saying so.
 * Rendered as given.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));
vi.mock("@/components/admin/csf/CsfQuestionnaire", () => ({
  CsfQuestionnaire: () => <div>questionnaire</div>,
}));

const S1 =
  "1 recorded answer belongs to ID.AM-09, a subcategory NIST CSF 2.0 does not" +
  " have, so it is not scored.";

const CATALOG = {
  functions: [],
  tiers: [
    { tier: 2, short_label: "Risk Informed", description: "" },
    { tier: 3, short_label: "Repeatable", description: "" },
  ],
  total_subcategories: 0,
} as unknown as CsfCatalog;

function assessment(over: Partial<CsfAssessment>): CsfAssessment {
  return {
    id: "a1",
    service_id: "s1",
    version: 1,
    status: "draft",
    approved_at: null,
    approved_by: null,
    answers: [],
    client_target_tier: 3,
    client_profile: null,
    ...over,
  } as CsfAssessment;
}

beforeEach(() => {
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue(CATALOG);
});

describe("CsfSelfAssessment states an answer kept on a retired subcategory (#852)", () => {
  it("renders the API's sentence", async () => {
    vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(
      assessment({ retired_answers: 1, retired_answers_note: S1 }),
    );
    render(<CsfSelfAssessment serviceId="s1" />);
    expect(await screen.findByTestId("csf-retired-answers")).toHaveTextContent(
      S1,
    );
  });

  it("says nothing when nothing was kept", async () => {
    vi.mocked(csfClient.fetchSelfAssessment).mockResolvedValue(
      assessment({ retired_answers: 0, retired_answers_note: null }),
    );
    render(<CsfSelfAssessment serviceId="s1" />);
    expect(await screen.findByText("questionnaire")).toBeVisible();
    expect(screen.queryByTestId("csf-retired-answers")).toBeNull();
  });
});
