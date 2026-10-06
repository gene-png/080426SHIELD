import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AttackAssessment,
  AttackCoverageRow,
  AttackOutsideCitation,
  CatalogTechnique,
} from "@/lib/attack/types";

import { AttackOutsideSubsetAlert } from "./AttackOutsideSubsetAlert";
import { AttackTechniquePanel } from "./AttackTechniquePanel";

/**
 * #851: rows crediting a tool outside the client's CURRENT security tool list.
 * Copy approved by the advisor (#736): S1, S2, S3b and S5 in the "not in"
 * wording, singular and plural. Asserted byte for byte.
 */

function assessment(
  status: AttackAssessment["status"],
  items: AttackOutsideCitation[],
): AttackAssessment {
  return {
    status,
    citations_outside_subset: items,
  } as unknown as AttackAssessment;
}

const LEGACY: AttackOutsideCitation = {
  technique_code: "T1003",
  field: "detection_tools",
  tool: "Legacy AV",
  locked: false,
};

describe("AttackOutsideSubsetAlert (#851)", () => {
  it("on a draft: S1, each row as S2, and S3b", () => {
    render(
      <AttackOutsideSubsetAlert
        assessment={assessment("draft", [
          LEGACY,
          { ...LEGACY, technique_code: "T1059", field: "response_tools", locked: true },
        ])}
        phase="draft"
      />,
    );
    const alert = screen.getByTestId("attack-outside-subset");
    expect(alert.querySelector("p")?.textContent).toBe(
      "2 technique rows credit a tool that is not in the client's security tool list, so their status may count a tool the client does not use:",
    );
    expect([...alert.querySelectorAll("li")].map((li) => li.textContent)).toEqual([
      "T1003, Detection: Legacy AV",
      "T1059, Response: Legacy AV (locked, so Run AI will not change it)",
    ]);
    expect(alert.textContent).toContain(
      "Remove the tool in the technique's panel, or unlock the row and use Run AI.",
    );
  });

  it("counts rows, not tools, and uses the singular for one row", () => {
    render(
      <AttackOutsideSubsetAlert
        assessment={assessment("draft", [
          LEGACY,
          { ...LEGACY, field: "prevention_tools" },
        ])}
        phase="draft"
      />,
    );
    expect(
      screen.getByTestId("attack-outside-subset").querySelector("p")?.textContent,
    ).toBe(
      "1 technique row credits a tool that is not in the client's security tool list, so its status may count a tool the client does not use:",
    );
  });

  it("once approved: S5, no remedy, and only in the approved instance", () => {
    const a = assessment("approved", [
      LEGACY,
      { ...LEGACY, technique_code: "T1059" },
    ]);
    const { rerender } = render(
      <AttackOutsideSubsetAlert assessment={a} phase="approved" />,
    );
    const alert = screen.getByTestId("attack-outside-subset");
    expect(alert.querySelector("p")?.textContent).toBe(
      "2 technique rows in this approved assessment credit a tool that is not in the client's security tool list. The deliverable counts that tool.",
    );
    expect(alert.textContent).not.toContain("Remove the tool");
    rerender(<AttackOutsideSubsetAlert assessment={a} phase="draft" />);
    expect(screen.queryByTestId("attack-outside-subset")).toBeNull();
  });

  it("renders nothing when no row credits such a tool", () => {
    const { rerender } = render(
      <AttackOutsideSubsetAlert assessment={assessment("draft", [LEGACY])} phase="draft" />,
    );
    expect(screen.getByTestId("attack-outside-subset")).toBeTruthy(); // positive first
    rerender(
      <AttackOutsideSubsetAlert assessment={assessment("draft", [])} phase="draft" />,
    );
    expect(screen.queryByTestId("attack-outside-subset")).toBeNull();
  });
});

const TECHNIQUE: CatalogTechnique = {
  id: "T1003",
  name: "OS Credential Dumping",
  tactics: ["TA0006"],
  is_sub_technique: false,
  parent_id: null,
};

function row(over: Partial<AttackCoverageRow> = {}): AttackCoverageRow {
  return {
    id: "c1",
    assessment_id: "a1",
    technique_code: "T1003",
    status: "covered",
    reason_code: null,
    narrative: null,
    notes: null,
    evidence_artifact_id: null,
    detection_tools: ["EDR Tool", "Legacy AV"],
    answered_by: null,
    answered_at: null,
    ...over,
  };
}

describe("AttackTechniquePanel, the Remove control (#851, D2)", () => {
  it("sends the narrow remove_tool for exactly that tool and list", () => {
    const onPatch = vi.fn();
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row()}
        coverageDefinitions={[]}
        onPatch={onPatch}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Remove Legacy AV from Detection" }),
    );
    expect(onPatch).toHaveBeenCalledWith({
      remove_tool: { field: "detection_tools", name: "Legacy AV" },
    });
    expect(
      screen.getByRole("button", { name: "Remove Legacy AV from Detection" })
        .textContent,
    ).toBe("Remove");
  });

  it("offers no Remove control on a read-only panel", () => {
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row()}
        coverageDefinitions={[]}
        readOnly
        onPatch={vi.fn()}
      />,
    );
    expect(screen.getByText("Legacy AV")).toBeTruthy(); // the tool is shown
    expect(
      screen.queryByRole("button", { name: "Remove Legacy AV from Detection" }),
    ).toBeNull();
  });
});
