import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtAnswer, ZtCatalog } from "@/lib/zt/types";

import { ZtQuestionnaire } from "./ZtQuestionnaire";

/**
 * Z1 and Z2, admin (#736 6204461502 section 6, approved at 6205956728):
 * - Z1 beside the stage picker of a capability with a stage set and blank
 *   notes: "Self-reported, not validated".
 * - Z2 once per questionnaire: "The highlighted stage is the current assessed
 *   score."
 */

const Z1 = "Self-reported, not validated";
const Z2_ADMIN = "The highlighted stage is the current assessed score.";

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
      capabilities: ["A", "B", "C", "D"].map((x) => ({
        code: `CISA.ID.0${x}`,
        name: `Cap ${x}`,
        outcome: "o",
      })),
    },
  ],
} as unknown as ZtCatalog;

function answer(code: string, stage: number | null, notes: string | null) {
  return {
    id: `ans-${code}`,
    capability_code: code,
    maturity_stage: stage,
    target_stage: null,
    notes,
    locked: false,
  } as unknown as ZtAnswer;
}

function renderQ(answers: ZtAnswer[]) {
  const byCode = Object.fromEntries(answers.map((a) => [a.capability_code, a]));
  return render(
    <ZtQuestionnaire
      catalog={CATALOG}
      answersByCode={byCode}
      onAnswerUpdate={() => {}}
    />,
  );
}

describe("ZtQuestionnaire Z1 and Z2 (admin)", () => {
  it("flags only a stage with blank notes, and shows the legend once", () => {
    renderQ([
      answer("CISA.ID.0A", 2, null), // stage, no notes: flagged
      answer("CISA.ID.0B", 3, "   "), // stage, whitespace notes: flagged
      answer("CISA.ID.0C", 2, "MFA everywhere."), // stage and notes: not
      answer("CISA.ID.0D", null, null), // no stage: not
    ]);
    // The positive state first.
    expect(screen.getAllByText(Z1)).toHaveLength(2);
    expect(screen.getAllByText(Z2_ADMIN)).toHaveLength(1);
    const flagged = screen
      .getAllByText(Z1)
      .map((el) => el.closest("li")?.textContent ?? "");
    expect(flagged.some((t) => t.includes("CISA.ID.0A"))).toBe(true);
    expect(flagged.some((t) => t.includes("CISA.ID.0B"))).toBe(true);
    expect(flagged.some((t) => t.includes("CISA.ID.0C"))).toBe(false);
    expect(flagged.some((t) => t.includes("CISA.ID.0D"))).toBe(false);
  });
});
