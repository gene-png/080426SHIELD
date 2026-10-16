import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ZtAnswer, ZtCatalog } from "@/lib/zt/types";

import { ZtQuestionnaire } from "./ZtQuestionnaire";

/** #922 on the consultant's screen: each picker honours its capability's max. */

const CATALOG = {
  framework: "dod_ztra",
  stages: [
    { stage: 1, label: "Below Target", description: "" },
    { stage: 2, label: "Target", description: "" },
    { stage: 3, label: "Advanced", description: "" },
  ],
  pillars: [
    {
      code: "USR",
      name: "User",
      purpose: "p",
      capabilities: [
        {
          code: "DOD.USR.01",
          pillar_code: "USR",
          name: "A",
          outcome: "o",
          max_stage: 2,
        },
        {
          code: "DOD.USR.02",
          pillar_code: "USR",
          name: "B",
          outcome: "o",
          max_stage: 3,
        },
      ],
    },
  ],
} as unknown as ZtCatalog;

function answer(code: string): ZtAnswer {
  return {
    id: `ans-${code}`,
    capability_code: code,
    maturity_stage: null,
    notes: null,
  } as unknown as ZtAnswer;
}

describe("ZtQuestionnaire #922", () => {
  it("makes Advanced unavailable only on the capability that cannot reach it", () => {
    render(
      <ZtQuestionnaire
        catalog={CATALOG}
        answersByCode={{
          "DOD.USR.01": answer("DOD.USR.01"),
          "DOD.USR.02": answer("DOD.USR.02"),
        }}
        onAnswerUpdate={() => {}}
      />,
    );
    const capped = screen.getByRole("radiogroup", {
      name: "Maturity stage for DOD.USR.01",
    });
    const open = screen.getByRole("radiogroup", {
      name: "Maturity stage for DOD.USR.02",
    });
    // The positive state first.
    expect(
      within(open).getByRole("radio", { name: "Advanced" }),
    ).not.toHaveAttribute("aria-disabled");
    expect(
      within(capped).getByRole("radio", { name: "Advanced" }),
    ).toHaveAttribute("aria-disabled", "true");
  });
});
