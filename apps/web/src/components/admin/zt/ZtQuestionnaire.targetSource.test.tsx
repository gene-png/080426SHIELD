import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtAnswer, ZtCatalog } from "@/lib/zt/types";

import { ZtQuestionnaire } from "./ZtQuestionnaire";

/**
 * #982 (A): a per-capability target whose origin is not recorded (every target
 * stored before migration 0076, some of them set by earlier AI runs) is
 * disclosed beside the Target select on the consultant's questionnaire. The
 * line was approved verbatim by the advisor; it is quoted here, never
 * imported.
 */

const NOT_RECORDED =
  "Who set this target is not recorded. An earlier AI run may have set it.";

const CATALOG = {
  framework: "cisa_ztmm_2_0",
  stages: [
    { stage: 1, label: "Traditional", description: "" },
    { stage: 2, label: "Initial", description: "" },
    { stage: 3, label: "Advanced", description: "" },
    { stage: 4, label: "Optimal", description: "" },
  ],
  pillars: [
    {
      code: "ID",
      name: "Identity",
      purpose: "p",
      capabilities: ["A", "B", "C"].map((x) => ({
        code: `CISA.ID.0${x}`,
        name: `Cap ${x}`,
        outcome: "o",
      })),
    },
  ],
} as unknown as ZtCatalog;

function answer(
  code: string,
  target: number | null,
  source: string | null,
): ZtAnswer {
  return {
    id: `ans-${code}`,
    capability_code: code,
    maturity_stage: null,
    target_stage: target,
    target_source: source,
    notes: "n",
    locked: false,
  } as unknown as ZtAnswer;
}

function row(code: string): HTMLElement {
  const li = screen.getByText(code).closest("li");
  if (!li) throw new Error(`no row for ${code}`);
  return li;
}

describe("ZtQuestionnaire #982: a target with no recorded origin", () => {
  it("is disclosed only where a target exists and its origin is not recorded", () => {
    render(
      <ZtQuestionnaire
        catalog={CATALOG}
        answersByCode={{
          "CISA.ID.0A": answer("CISA.ID.0A", 3, null), // not recorded
          "CISA.ID.0B": answer("CISA.ID.0B", 3, "consultant"), // recorded
          "CISA.ID.0C": answer("CISA.ID.0C", null, null), // no target
        }}
        onAnswerUpdate={() => {}}
      />,
    );
    // The positive state first.
    expect(
      within(row("CISA.ID.0A")).getByText(NOT_RECORDED),
    ).toBeInTheDocument();
    expect(within(row("CISA.ID.0B")).queryByText(NOT_RECORDED)).toBeNull();
    expect(within(row("CISA.ID.0C")).queryByText(NOT_RECORDED)).toBeNull();
    expect(screen.getAllByText(NOT_RECORDED)).toHaveLength(1);
  });
});
