import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AttackAssessment } from "@/lib/attack/types";

import { AttackOutsideSubsetAlert } from "./AttackOutsideSubsetAlert";

/**
 * #889 R4 on the ADMIN ATT&CK workspace (advisor, #736 6093188709): the API
 * sends the "not checked" sentence (C5, or C5b when the client's list has no
 * security tools) and the C8a / C8b lines; this panel renders them. Copy
 * written out here, never imported.
 */

const C5 =
  "The tools cited here were not checked against a security tool list, because the client has none.";
const C5B =
  "The tools cited here were not checked against a security tool list, because the client's security tool list has no security tools.";
const C8A =
  'In Acme Tech Debt, the newest security tool list (version 2, a draft) has no security tools, so these checks use version 1. If version 2 came from the wrong document, use "Discard draft" in that Tech Debt workspace.';

function assessment(extra: Partial<AttackAssessment>): AttackAssessment {
  return {
    status: "draft",
    citations_outside_subset: [],
    ...extra,
  } as unknown as AttackAssessment;
}

describe("AttackOutsideSubsetAlert, R4 (#889)", () => {
  it("renders the API's not-checked sentence: C5b when the list is empty", () => {
    render(
      <AttackOutsideSubsetAlert
        assessment={assessment({
          subset_checked: false,
          subset_not_checked_sentence: C5B,
          subset_fallback_notes: [],
        })}
        phase="draft"
      />,
    );
    expect(
      screen.getByTestId("attack-outside-subset-not-checked").textContent,
    ).toBe(C5B);
    expect(screen.queryByText(C5)).toBeNull();
  });

  it("renders C8a when an earlier version is used, with nothing outside", () => {
    render(
      <AttackOutsideSubsetAlert
        assessment={assessment({
          subset_checked: true,
          subset_not_checked_sentence: null,
          subset_fallback_notes: [C8A],
        })}
        phase="draft"
      />,
    );
    expect(screen.getByText(C8A)).toBeInTheDocument();
    expect(
      screen.queryByTestId("attack-outside-subset-not-checked"),
    ).toBeNull();
  });
});
