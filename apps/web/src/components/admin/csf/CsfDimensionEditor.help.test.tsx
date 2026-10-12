import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfDimensionScore } from "@/lib/csf/types";

import { CsfDimensionEditor } from "./CsfDimensionEditor";

/**
 * C-2 (#1056): the on-screen instructions for "Edit dimension scores".
 *
 * Every expected string below is TYPED HERE, from the copy the advisor
 * approved verbatim (#736, 6115345112) -- never imported from
 * `@/lib/csf/editorHelp`, so a test cannot agree with the copy by
 * construction (CLAUDE.md, #72).
 *
 * The numbers in that copy come from the SPEC, not from the engine:
 * reference-docs/SHIELDv2_Master_Spec.txt, "Total: 0-10. Mapped to Maturity
 * Level 1-5: 0-2 -> Level 1 ... 3-5 -> Level 2 ... 6-7 -> Level 3 ... 8-9 ->
 * Level 4 ... 10 -> Level 5", and "Evidence rule: If evidence cannot be
 * produced, Implementation cannot exceed 1 AND total maturity cannot exceed
 * Level 2." The engine side is pinned to the same spec literals,
 * independently, by `test_maturity_level_mapping`,
 * `test_evidence_cap_clamps_implementation_and_level` and
 * `test_evidence_cap_by_level_clamp` in apps/api/tests/unit/test_csf_playbook.py.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchProfile: vi.fn(),
  patchDimensionScore: vi.fn(),
}));

function row(overrides: Partial<CsfDimensionScore> = {}): CsfDimensionScore {
  // A state the writer produces: all five dimensions 2 WITH evidence is total
  // 10, level 5, uncapped (`score_tier`).
  return {
    id: "row-1",
    tier: "high",
    subcategory_code: "GV.OC-01",
    governance: 2,
    policy: 2,
    implementation: 2,
    monitoring: 2,
    improvement: 2,
    in_scope: true,
    rationale: null,
    what_we_found: null,
    has_evidence: true,
    target_level: 3,
    locked: false,
    total: 10,
    level: 5,
    evidence_capped: false,
    ...overrides,
  };
}

// The capped state the engine produces for the same scores WITHOUT evidence:
// Implementation counts as 1 (total 9) and the level stops at 2
// (`test_evidence_cap_clamps_implementation_and_level`). The STORED
// implementation stays 2, which is what the editor shows (`_score_response`).
const CAPPED = {
  has_evidence: false,
  total: 9,
  level: 2,
  evidence_capped: true,
} as const;

async function renderWith(r: CsfDimensionScore) {
  vi.mocked(csfClient.fetchProfile).mockResolvedValue({
    tier: "high",
    rows: [r],
  });
  render(<CsfDimensionEditor serviceId="svc-1" />);
  // Positive state first: the row has loaded (CLAUDE.md, assert what must
  // APPEAR before what must not).
  await screen.findByRole("radiogroup", { name: "Governance" });
}

function openHelp(): HTMLElement {
  fireEvent.click(screen.getByText("How to score a row"));
  return screen.getByTestId("csf-editor-help");
}

const H1 =
  "Score each of the five dimensions 0, 1 or 2 for this subcategory, for the systems in the selected impact tier. 0 means not demonstrated, 1 means partial or informal, and 2 means established: formal, consistently performed, and applied across the tier's systems. When a score is between two values, choose the lower one unless the notes or evidence show the higher one is met. These are the same definitions Run AI is told to use.";
const H2_INTRO =
  "The five scores add up to a total from 0 to 10, and the total sets the maturity level:";
const H2_BANDS = [
  "0 to 2: L1",
  "3 to 5: L2",
  "6 to 7: L3",
  "8 to 9: L4",
  "10: L5",
];
const H3 =
  'Tick "Evidence on file" only when evidence for this subcategory and tier is held. Without it, Implementation counts as no more than 1 and the level cannot exceed L2, whatever the scores. Run AI never ticks this box, and a file the client attached to the questionnaire does not tick it either: a consultant has to.';
const H4 =
  'Target is the level the client should reach for this subcategory in this tier. The Enterprise profile compares its rolled-up level, usually the lowest of the in-scope tiers that have been scored, with the highest target set on any in-scope tier that has been scored. Below the target is a gap. With no target on any in-scope tier that has been scored, the subcategory is not checked for a gap: it is counted as "with no target", not as met.';
const H5 =
  'Untick "In scope" when this subcategory does not apply to the systems in this tier. An out-of-scope row is left out of the Enterprise level, the gaps and their priorities. If every tier is out of scope, the subcategory leaves the Enterprise profile.';
const H6 =
  '"Lock vs AI reruns" stops Run AI from changing this row\'s scores and findings. You can still edit a locked row yourself. Without a lock, a later live Run AI can replace scores you entered. Edits are paused while a run is in progress.';

const HINTS: [string, string][] = [
  [
    "Governance",
    "Ownership, accountability, authority and oversight for this outcome.",
  ],
  [
    "Policy & Process",
    "A documented, approved and followed policy, process, plan or procedure.",
  ],
  [
    "Implementation",
    "The outcome is actually performed. Planned or documented-only scores 0.",
  ],
  [
    "Monitoring & Measurement",
    "Monitoring, testing or review on a defined cadence. Logging alone is not monitoring.",
  ],
  [
    "Continuous Improvement",
    "A recurring cycle that uses lessons learned and findings to improve. One fix is not a cycle.",
  ],
];

const RUBRIC: string[][] = [
  ["Dimension", "0", "1", "2"],
  [
    "Governance",
    "No ownership or oversight shown",
    "Informal, unclear or partial",
    "Formal ownership and oversight, consistently exercised",
  ],
  [
    "Policy & Process",
    "No policy or process shown",
    "Exists but informal, draft, outdated or partly followed",
    "Documented, approved, current and repeatably followed",
  ],
  [
    "Implementation",
    "Not performed, or only planned",
    "Partial, ad hoc or part of the tier",
    "Fully and consistently implemented across the tier",
  ],
  [
    "Monitoring & Measurement",
    "No monitoring or review shown",
    "Informal, irregular or without defined measures",
    "Defined measures on an established cadence",
  ],
  [
    "Continuous Improvement",
    "No improvement mechanism shown",
    "Reactive or untracked improvements",
    "A defined, recurring improvement process",
  ],
];

const S1 =
  "Without evidence, Implementation counts as no more than 1 in the total, and the level cannot go above L2.";
const S2 =
  "No target on this tier. The subcategory is still checked for a gap if another in-scope tier that has been scored has a target.";

beforeEach(() => {
  vi.mocked(csfClient.fetchProfile).mockReset();
});

describe("CsfDimensionEditor instructions (C-2, #1056)", () => {
  it("collapses the instructions by default and opens them on the summary", async () => {
    await renderWith(row());
    const summary = screen.getByText("How to score a row");
    expect(summary).toBeVisible();
    expect(screen.getByText(H1)).not.toBeVisible();
    fireEvent.click(summary);
    expect(screen.getByText(H1)).toBeVisible();
  });

  it("states the scale, the level bands, the cap, Target, In scope and Lock verbatim", async () => {
    await renderWith(row());
    const help = openHelp();
    const paragraphs = Array.from(help.querySelectorAll("p")).map(
      (p) => p.textContent,
    );
    for (const text of [H1, H2_INTRO, H3, H4, H5, H6]) {
      expect(paragraphs).toContain(text);
    }
    const bands = Array.from(help.querySelectorAll("li")).map(
      (li) => li.textContent,
    );
    expect(bands).toEqual(H2_BANDS);
  });

  it("carries the 0/1/2 rubric table, row by row", async () => {
    await renderWith(row());
    const table = within(openHelp()).getByRole("table");
    const cells = Array.from(table.querySelectorAll("tr")).map((tr) =>
      Array.from(tr.querySelectorAll("th, td")).map((c) => c.textContent),
    );
    expect(cells).toEqual(RUBRIC);
  });

  it("describes each dimension's radiogroup with its one-line hint", async () => {
    await renderWith(row());
    for (const [label, hint] of HINTS) {
      expect(
        screen.getByRole("radiogroup", { name: label }),
      ).toHaveAccessibleDescription(hint);
    }
  });

  it("explains the cap beside a capped total, and only there", async () => {
    await renderWith(row(CAPPED));
    expect(screen.getByText(S1)).toBeVisible();
  });

  it("explains the cap on a row capped by the level clamp alone", async () => {
    // #1076 finding 1: `score_tier` also caps a row whose Implementation is
    // already 0 or 1, through the level clamp alone. G2 P2 I0 M2 C2 without
    // evidence: total 8 (L4 by the bands), held at L2, Implementation still 0
    // (pinned engine-side by the `((2, 2, 0, 2, 2), False, 8, 2, True)` case
    // of `test_evidence_cap_by_level_clamp` in test_csf_playbook.py). S1 must
    // hold here too.
    await renderWith(row({ ...CAPPED, implementation: 0, total: 8, level: 2 }));
    expect(screen.getByText(S1)).toBeVisible();
  });

  it("says nothing about the cap on an uncapped row", async () => {
    await renderWith(row());
    expect(screen.queryByText(S1)).toBeNull();
  });

  it("explains a row with no target on its tier, and only then", async () => {
    await renderWith(row({ target_level: null }));
    expect(screen.getByText(S2)).toBeVisible();
  });

  it("says nothing about a missing target when one is set", async () => {
    await renderWith(row({ target_level: 3 }));
    expect(screen.getByRole("combobox", { name: "Target" })).toBeVisible();
    expect(screen.queryByText(S2)).toBeNull();
  });
});
