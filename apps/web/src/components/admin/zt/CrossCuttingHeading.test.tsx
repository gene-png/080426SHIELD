import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ZtSelfAssessment } from "@/components/self-assessment/ZtSelfAssessment";
import * as ztClient from "@/lib/zt/client";
import type { ZtAnswer, ZtAssessment, ZtCatalog } from "@/lib/zt/types";

import { ZtQuestionnaire } from "./ZtQuestionnaire";

/**
 * #838: CISA ZTMM 2.0 tabulates each pillar's Visibility and Analytics,
 * Automation and Orchestration and Governance rows after its functions, and
 * both questionnaires put the approved "Cross-cutting" sub-heading once, before
 * the first of them. Driven through BOTH components that render it (the
 * consultant's and the client's), because the heading is placed by each
 * component's own map, not by the helper.
 *
 * The catalog is shaped like the API's (`GET /zt/catalog`): codes, `kind`
 * values and order as `app/zt/catalog.py` emits them for Identity.
 */

vi.mock("@/lib/zt/client", () => ({
  ZtProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchSelfAssessment: vi.fn(),
  patchSelfAssessmentAnswer: vi.fn(),
  submitSelfAssessment: vi.fn(),
}));

function cap(code: string, name: string, kind: "function" | "cross_cutting") {
  return { code, pillar_code: "ID", name, outcome: "CISA Optimal: x", kind };
}

const CISA: ZtCatalog = {
  framework: "cisa_ztmm_2_0",
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "Who is asking.",
      capabilities: [
        cap("CISA.ID.01", "Authentication", "function"),
        cap("CISA.ID.02", "Identity Stores", "function"),
        cap("CISA.ID.VA", "Visibility and Analytics", "cross_cutting"),
        cap("CISA.ID.AO", "Automation and Orchestration", "cross_cutting"),
        cap("CISA.ID.GV", "Governance", "cross_cutting"),
      ],
    },
  ],
  stages: [
    { stage: 1, label: "Traditional", description: "" },
    { stage: 2, label: "Initial", description: "" },
    { stage: 3, label: "Advanced", description: "" },
    { stage: 4, label: "Optimal", description: "" },
  ],
  total_capabilities: 5,
};

/** A catalog with no cross-cutting rows: DoD's, whose rows carry no `kind`. */
const FUNCTIONS_ONLY: ZtCatalog = {
  ...CISA,
  pillars: [
    {
      ...CISA.pillars[0]!,
      capabilities: CISA.pillars[0]!.capabilities.slice(0, 2).map((c) => ({
        code: c.code,
        pillar_code: c.pillar_code,
        name: c.name,
        outcome: c.outcome,
      })),
    },
  ],
  total_capabilities: 2,
};

function answer(code: string): ZtAnswer {
  return {
    id: `ans-${code}`,
    assessment_id: "a1",
    capability_code: code,
    maturity_stage: null,
    target_stage: null,
    notes: null,
    evidence_artifact_id: null,
    locked: false,
    answered_by: null,
    answered_at: null,
  } as ZtAnswer;
}

function answersFor(catalog: ZtCatalog): ZtAnswer[] {
  return catalog.pillars.flatMap((p) =>
    p.capabilities.map((c) => answer(c.code)),
  );
}

/** The text of each item of the list the heading sits in, in order. */
function itemsAround(heading: HTMLElement): string[] {
  const list = heading.closest("ul");
  expect(list).not.toBeNull();
  return Array.from(list!.children).map((li) => li.textContent ?? "");
}

function expectHeadingBeforeFirstCrossCuttingRow(): void {
  const headings = screen.getAllByRole("heading", { name: "Cross-cutting" });
  expect(headings).toHaveLength(1);
  const order = itemsAround(headings[0]!);
  const at = order.findIndex((t) => t === "Cross-cutting");
  expect(order[at - 1]).toContain("CISA.ID.02");
  expect(order[at + 1]).toContain("CISA.ID.VA");
}

describe("the Cross-cutting sub-heading (#838)", () => {
  it("the consultant's questionnaire puts it once, before the first cross-cutting row", () => {
    const answersByCode = Object.fromEntries(
      answersFor(CISA).map((a) => [a.capability_code, a]),
    );
    render(
      <ZtQuestionnaire
        catalog={CISA}
        answersByCode={answersByCode}
        onAnswerUpdate={() => {}}
      />,
    );
    expectHeadingBeforeFirstCrossCuttingRow();
  });

  it("the consultant's questionnaire has none for a pillar with no cross-cutting row", () => {
    const answersByCode = Object.fromEntries(
      answersFor(FUNCTIONS_ONLY).map((a) => [a.capability_code, a]),
    );
    render(
      <ZtQuestionnaire
        catalog={FUNCTIONS_ONLY}
        answersByCode={answersByCode}
        onAnswerUpdate={() => {}}
      />,
    );
    // What must appear, before what must not.
    expect(screen.getByText("CISA.ID.02")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Cross-cutting" }),
    ).not.toBeInTheDocument();
  });

  describe("the client's self-assessment", () => {
    beforeEach(() => {
      vi.mocked(ztClient.fetchCatalog).mockResolvedValue(CISA);
      vi.mocked(ztClient.fetchSelfAssessment).mockResolvedValue({
        id: "a1",
        service_id: "s1",
        framework: "cisa_ztmm_2_0",
        version: 1,
        status: "draft",
        approved_at: null,
        approved_by: null,
        answers: answersFor(CISA),
        client_target_stage: 3,
      } as ZtAssessment);
    });

    it("puts it once, before the first cross-cutting row", async () => {
      render(<ZtSelfAssessment serviceId="s1" framework="cisa_ztmm_2_0" />);
      await screen.findByLabelText("Notes for CISA.ID.VA");
      expectHeadingBeforeFirstCrossCuttingRow();
    });
  });
});
