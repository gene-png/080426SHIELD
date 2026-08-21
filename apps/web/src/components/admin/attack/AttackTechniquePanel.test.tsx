import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AttackCoverageRow,
  CatalogTechnique,
  UnconfirmedCitation,
} from "@/lib/attack/types";

import { AttackTechniquePanel } from "./AttackTechniquePanel";

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
    notes: null,
    evidence_artifact_id: null,
    detection_tools: ["CrowdStrike Falcon"],
    answered_by: null,
    answered_at: null,
    ...over,
  };
}

const INFERRED: UnconfirmedCitation = {
  tool: "CrowdStrike Falcon",
  cited: "CrowdStrike",
  reason: "substring",
  field: "detection_tools",
  cleared_at: null,
};

const REJECTED: UnconfirmedCitation = {
  tool: null,
  cited: "Qradar",
  reason: "rejected_unknown",
  field: "detection_tools",
  cleared_at: null,
};

function panel(coverage: AttackCoverageRow, onConfirm = vi.fn()) {
  return render(
    <AttackTechniquePanel
      technique={TECHNIQUE}
      coverage={coverage}
      coverageDefinitions={[]}
      onPatch={vi.fn()}
      onConfirmCitations={onConfirm}
    />,
  );
}

describe("AttackTechniquePanel — the review queue (#101)", () => {
  it("shows WHAT the model wrote, not only what it was resolved to", () => {
    // #101's point: "Qradar" tells a consultant the list holds something else.
    // The resolved name tells them nothing about why the citation needed
    // rescuing, so a queue showing only `tool` cannot be worked through.
    panel(row({ pending_review: true, unconfirmed_citations: [INFERRED] }));
    const queue = screen.getByTestId("attack-citation-queue");
    expect(queue).toHaveTextContent(/CrowdStrike Falcon/);
    expect(queue).toHaveTextContent(/CrowdStrike/);
  });

  it("shows a rejected citation even though it applied no tool", () => {
    // The entry that carries no tool at all is the one that explains an empty
    // Detection row. Hiding it because there is no name to show would leave the
    // consultant looking at a `covered` technique with no evidence and no reason.
    panel(
      row({
        pending_review: true,
        detection_tools: [],
        unconfirmed_citations: [REJECTED],
      }),
    );
    const queue = screen.getByTestId("attack-citation-queue");
    expect(queue).toHaveTextContent(/Qradar/);
  });

  it("offers confirming as its own action, and calls it", () => {
    const onConfirm = vi.fn();
    panel(
      row({ pending_review: true, unconfirmed_citations: [INFERRED] }),
      onConfirm,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /confirm this evidence/i }),
    );
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("says nothing when the row has no outstanding citations", () => {
    // Positive assertion first: a queryBy-toBeNull on a panel that failed to
    // render at all would pass over a deleted feature.
    panel(row({ pending_review: false, unconfirmed_citations: [] }));
    expect(screen.getByText(/OS Credential Dumping/)).toBeInTheDocument();
    expect(screen.queryByTestId("attack-citation-queue")).toBeNull();
  });

  it("still shows a CLEARED entry, marked as accepted, with no button", () => {
    // Stamped, not deleted. "A human accepted this" and "nobody ever cited it"
    // are different answers to why this technique counts, and the panel is where
    // that question gets asked.
    panel(
      row({
        pending_review: false,
        unconfirmed_citations: [
          { ...INFERRED, cleared_at: "2026-08-21T00:00:00Z" },
        ],
      }),
    );
    const queue = screen.getByTestId("attack-citation-queue");
    expect(queue).toHaveTextContent(/confirmed/i);
    expect(
      screen.queryByRole("button", { name: /confirm this evidence/i }),
    ).toBeNull();
  });

  it("does not offer confirming on a read-only assessment", () => {
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({
          pending_review: true,
          unconfirmed_citations: [INFERRED],
        })}
        coverageDefinitions={[]}
        readOnly
        onPatch={vi.fn()}
        onConfirmCitations={vi.fn()}
      />,
    );
    expect(screen.getByTestId("attack-citation-queue")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /confirm this evidence/i }),
    ).toBeNull();
  });
});
