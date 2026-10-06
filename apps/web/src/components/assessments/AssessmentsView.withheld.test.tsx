import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as intakeClient from "@/lib/intake/client";
import type { AssessmentResponse } from "@/lib/intake/types";

import { AssessmentsView } from "./AssessmentsView";

/**
 * #588: a report released over an assessment scored against another ATT&CK
 * catalog is WITHHELD from the client (#556). The home page says "Report
 * withheld"; this page read only the lifecycle status and called it released.
 */
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/lib/intake/client", () => ({
  fetchAssessments: vi.fn(),
  createAssessment: vi.fn(),
}));

function engagement(over: Partial<AssessmentResponse>): AssessmentResponse {
  return {
    service_id: "svc-1",
    service_type: "attack_coverage",
    title: "ATT&CK review",
    status: "released",
    assessment_status: null,
    withheld: false,
    created_at: "2026-09-01T12:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("AssessmentsView, a withheld report (#588)", () => {
  it("says 'Report withheld', not released, when every report is withheld", async () => {
    vi.mocked(intakeClient.fetchAssessments).mockResolvedValue([
      engagement({ withheld: true }),
    ]);
    render(<AssessmentsView />);
    expect(await screen.findByText("Report withheld")).toBeInTheDocument();
    expect(screen.queryByText(/released/i)).toBeNull();
  });

  it("says so over a self-assessment whose lifecycle says released", async () => {
    vi.mocked(intakeClient.fetchAssessments).mockResolvedValue([
      engagement({
        service_type: "nist_csf",
        assessment_status: "released",
        withheld: true,
      }),
    ]);
    render(<AssessmentsView />);
    expect(await screen.findByText("Report withheld")).toBeInTheDocument();
    expect(screen.queryByText("Report released")).toBeNull();
  });

  it("keeps the lifecycle label for a readable report", async () => {
    vi.mocked(intakeClient.fetchAssessments).mockResolvedValue([
      engagement({ service_type: "nist_csf", assessment_status: "released" }),
    ]);
    render(<AssessmentsView />);
    expect(await screen.findByText("Report released")).toBeInTheDocument();
    expect(screen.queryByText("Report withheld")).toBeNull();
  });
});
