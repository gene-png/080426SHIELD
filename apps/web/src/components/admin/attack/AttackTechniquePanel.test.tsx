import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AttackCoverageRow,
  CatalogReasonCode,
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
    reason_code: null,
    narrative: null,
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

// #109. Carries `tool: null` exactly like REJECTED, which is why the copy has
// to branch on the REASON: the value never reached a lookup, so "not on the
// approved list" is a verdict nothing produced.
const UNUSABLE_FIELD: UnconfirmedCitation = {
  tool: null,
  cited: "CrowdStrike Falcon",
  reason: "unusable_field",
  field: "detection_tools",
  cleared_at: null,
};

const UNUSABLE_ENTRY: UnconfirmedCitation = {
  tool: null,
  cited: null,
  reason: "unusable_entry",
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

describe("AttackTechniquePanel — a pending row with NO stored entries", () => {
  it("explains why it is withheld instead of showing a bare badge", () => {
    // Found by the §14 audit. A row is also pending when
    // `unconfirmed_citations` is NULL — the pre-resolver state — and the whole
    // review block was gated on `citations.length > 0`. The consultant saw a
    // "Pending review" badge, an empty panel, and no route out.
    //
    // This row really is reachable: a LOCKED row inside a DRAFT assessment is
    // skipped by Run-AI, skipped by migration 0045 (its parent is a draft), and
    // 409s on confirm-citations because nothing is outstanding.
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({ pending_review: true, unconfirmed_citations: null })}
        coverageDefinitions={[]}
        onPatch={vi.fn()}
        onConfirmCitations={vi.fn()}
      />,
    );
    const queue = screen.getByTestId("attack-citation-queue");
    expect(queue).toHaveTextContent(/never resolved/i);
    expect(queue).toHaveTextContent(/held out of the coverage score/i);
    // And it names the action that actually works, which is not "confirm" —
    // there is nothing stored to confirm.
    expect(queue).toHaveTextContent(/set the status or the tools/i);
    expect(
      screen.queryByRole("button", { name: /confirm this evidence/i }),
    ).toBeNull();
  });

  it("does not tell a consultant a wrongly-shaped citation was off the list", () => {
    // #109, and it is a copy defect rather than a rendering one. The entry has
    // `tool: null` like a rejection, so the rejection sentence claimed the
    // model named something "not on the approved list". The resolver never
    // looked it up -- the value arrived in the wrong SHAPE -- so the model may
    // well have named a tool that IS on the list, which is exactly what the
    // consultant needs to know to fix the run.
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({
          pending_review: true,
          unconfirmed_citations: [UNUSABLE_FIELD],
        })}
        coverageDefinitions={[]}
        onPatch={vi.fn()}
        onConfirmCitations={vi.fn()}
      />,
    );
    const queue = screen.getByTestId("attack-citation-queue");
    expect(queue).toHaveTextContent(/where a list of tool names belongs/i);
    expect(queue).toHaveTextContent(/CrowdStrike Falcon/);
    expect(queue).not.toHaveTextContent(/not on the approved list/i);
  });

  it("says a nameless entry was skipped rather than quoting an em dash", () => {
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({
          pending_review: true,
          unconfirmed_citations: [UNUSABLE_ENTRY],
        })}
        coverageDefinitions={[]}
        onPatch={vi.fn()}
        onConfirmCitations={vi.fn()}
      />,
    );
    const queue = screen.getByTestId("attack-citation-queue");
    expect(queue).toHaveTextContent(/was empty or was not text/i);
    // The old path rendered `Cited "—"`, which quotes a character the model
    // never sent back at the person trying to work out what it sent.
    expect(queue).not.toHaveTextContent(/Cited "—"/);
  });

  it("stays silent for a row that is neither pending nor flagged", () => {
    render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({ pending_review: false, unconfirmed_citations: null })}
        coverageDefinitions={[]}
        onPatch={vi.fn()}
        onConfirmCitations={vi.fn()}
      />,
    );
    expect(screen.getByText(/OS Credential Dumping/)).toBeInTheDocument();
    expect(screen.queryByTestId("attack-citation-queue")).toBeNull();
  });
});

// What the catalog serves, abridged: two Partial codes, the N/A code, and one
// for a status no writer may set yet -- the panel must filter by the ROW's
// status, never offer the whole list.
const REASONS: CatalogReasonCode[] = [
  {
    code: "reach_limited",
    status: "partial",
    definition: "Covered on the main estate, not on part of it.",
  },
  {
    code: "missing_control_category",
    status: "partial",
    definition: "A named category of control is absent.",
  },
  {
    code: "platform_absent",
    status: "not_applicable",
    definition: "The platform the technique targets is not present.",
  },
  {
    code: "adversary_preparation",
    status: "outside_control_surface",
    definition: "Activity on the adversary's own infrastructure.",
  },
];

function reasonPanel(coverage: AttackCoverageRow, onPatch = vi.fn()) {
  render(
    <AttackTechniquePanel
      technique={TECHNIQUE}
      coverage={coverage}
      coverageDefinitions={[]}
      reasonCodes={REASONS}
      onPatch={onPatch}
    />,
  );
  return onPatch;
}

function optionValues(): string[] {
  const select = screen.getByRole("combobox", { name: "Reason for T1003" });
  return Array.from(select.querySelectorAll("option")).map((o) => o.value);
}

describe("AttackTechniquePanel — reason code (#554)", () => {
  it("offers a Partial row only the Partial codes, and no-reason", () => {
    reasonPanel(row({ status: "partial" }));
    expect(optionValues()).toEqual([
      "",
      "reach_limited",
      "missing_control_category",
    ]);
    // D-076: the label promises no gate. The release gate is not built yet,
    // and a label claiming it is would license leaving Partials reasonless.
    const blank = screen
      .getByRole("combobox", { name: "Reason for T1003" })
      .querySelector('option[value=""]');
    expect(blank?.textContent).toBe("No reason given");
  });

  it("offers an N/A row only platform_absent -- never a missing control", () => {
    reasonPanel(row({ status: "not_applicable" }));
    expect(optionValues()).toEqual(["", "platform_absent"]);
  });

  it("offers no reason for a status that takes none", () => {
    reasonPanel(row({ status: "gap" }));
    expect(
      screen.queryByRole("combobox", { name: "Reason for T1003" }),
    ).not.toBeInTheDocument();
  });

  it("saves the chosen code", () => {
    const onPatch = reasonPanel(row({ status: "partial" }));
    fireEvent.change(
      screen.getByRole("combobox", { name: "Reason for T1003" }),
      {
        target: { value: "reach_limited" },
      },
    );
    expect(onPatch).toHaveBeenCalledWith({ reason_code: "reach_limited" });
  });

  it("shows the stored reason's definition", () => {
    reasonPanel(
      row({ status: "partial", reason_code: "missing_control_category" }),
    );
    expect(screen.getByTestId("reason-definition")).toHaveTextContent(
      "A named category of control is absent.",
    );
  });

  it("clears the reason with the no-reason option, sending null", () => {
    const onPatch = reasonPanel(
      row({ status: "partial", reason_code: "reach_limited" }),
    );
    fireEvent.change(
      screen.getByRole("combobox", { name: "Reason for T1003" }),
      {
        target: { value: "" },
      },
    );
    expect(onPatch).toHaveBeenCalledWith({ reason_code: null });
  });

  it("shows a stored narrative, and saves an edit on blur", () => {
    const onPatch = reasonPanel(
      row({ status: "gap", narrative: "Agent coverage unknown." }),
    );
    const box = screen.getByRole("textbox", {
      name: "What could not be established for T1003",
    });
    expect(box).toHaveValue("Agent coverage unknown.");
    fireEvent.change(box, {
      target: { value: "Agent coverage on servers unknown." },
    });
    fireEvent.blur(box);
    expect(onPatch).toHaveBeenCalledWith({
      narrative: "Agent coverage on servers unknown.",
    });
  });
});

describe("AttackTechniquePanel — narrative limits (#603 review)", () => {
  function box() {
    return screen.getByRole("textbox", {
      name: "What could not be established for T1003",
    });
  }

  it("caps the narrative at the API's 8000 characters", () => {
    reasonPanel(row({ status: "gap", narrative: "x" }));
    expect(box()).toHaveAttribute("maxLength", "8000");
  });

  it("sends null, never an empty string, when the narrative is cleared", () => {
    const onPatch = reasonPanel(
      row({ status: "gap", narrative: "Was unknown." }),
    );
    fireEvent.change(box(), { target: { value: "   " } });
    fireEvent.blur(box());
    expect(onPatch).toHaveBeenCalledWith({ narrative: null });
  });

  it("shows the stored narrative again after a refused save rolls back", () => {
    const { rerender } = render(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({ id: "c2", status: "gap", narrative: "Stored." })}
        coverageDefinitions={[]}
        reasonCodes={REASONS}
        onPatch={vi.fn()}
      />,
    );
    const textbox = screen.getAllByRole("textbox", {
      name: "What could not be established for T1003",
    })[0];
    fireEvent.change(textbox, { target: { value: "Unsaved edit" } });
    // The workspace applies the edit optimistically, then rolls back to the
    // stored row when the API refuses it.
    rerender(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({ id: "c2", status: "gap", narrative: "Unsaved edit" })}
        coverageDefinitions={[]}
        reasonCodes={REASONS}
        onPatch={vi.fn()}
      />,
    );
    rerender(
      <AttackTechniquePanel
        technique={TECHNIQUE}
        coverage={row({ id: "c2", status: "gap", narrative: "Stored." })}
        coverageDefinitions={[]}
        reasonCodes={REASONS}
        onPatch={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("textbox", {
        name: "What could not be established for T1003",
      }),
    ).toHaveValue("Stored.");
  });
});
