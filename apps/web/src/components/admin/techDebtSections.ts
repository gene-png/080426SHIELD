/**
 * #1376, the Tech Debt pilot of the UI section split: which section of the
 * client frame shows each block of `TechDebtWorkspace`, and the copy the
 * sections add. The table is the component map the PR body carries, so a test
 * reads "every block lands in a section" from here rather than from prose.
 *
 * A block listed under more than one section is deliberate and says why in
 * its comment. Every other block is in exactly one.
 *
 * PENDING advisor approval, verbatim: every string in `TD_SECTION_COPY`. The
 * section titles are Gene's tab names (`SECTIONS` labels), not new copy.
 */
import type { SectionKey } from "@/components/service-shell/SectionBar";
import type { Visibility } from "@/components/service-shell/SectionHeader";

export type TdBlock =
  /** The list's status pill: a state the reader needs in every section. */
  | "listStatus"
  /** The refresh-failure band and the load-error card: a failed read shows
   *  wherever the reader is. */
  | "readFailures"
  | "progressStages"
  | "keyFigures"
  | "upload"
  | "documents"
  | "reconciliation"
  /** One line under the totals, saying they cover the included rows only:
   *  the box that explains it is in Inputs, but the totals are read in
   *  Overview and Review. */
  | "reconciliationNote"
  /** Run status, "Extracting…", the extract error and the outcome-unknown
   *  alert. Extraction is STARTED from Inputs (the upload, or "Extract from
   *  this"), and the errors are this page's state, so they show there as well
   *  as in AI draft: shown only in AI draft, a failure would be invisible on
   *  the page where it happened. */
  | "runProgress"
  | "aiSource"
  | "resultCard"
  | "listHeading"
  | "securityQueue"
  | "extractionFindings"
  | "reviewTable"
  | "approve"
  | "consolidationPlan"
  | "savingsWhatIf"
  | "overlap"
  | "deliverableGenerate"
  | "deliverablePreview"
  | "deliverableRelease"
  | "recommendationsEmpty";

export const TD_BLOCK_SECTIONS: Record<TdBlock, readonly SectionKey[]> = {
  listStatus: [
    "overview",
    "inputs",
    "ai-draft",
    "review",
    "analysis",
    "generate",
    "quality-check",
    "approve-and-release",
  ],
  readFailures: [
    "overview",
    "inputs",
    "ai-draft",
    "review",
    "analysis",
    "generate",
    "quality-check",
    "approve-and-release",
  ],
  progressStages: ["overview"],
  keyFigures: ["overview"],
  upload: ["inputs"],
  documents: ["inputs"],
  reconciliation: ["inputs"],
  reconciliationNote: ["overview", "review"],
  runProgress: ["inputs", "ai-draft"],
  aiSource: ["ai-draft"],
  resultCard: ["ai-draft"],
  listHeading: ["review"],
  securityQueue: ["review"],
  // "Correct these in the table below": the findings sit above the table.
  extractionFindings: ["review"],
  reviewTable: ["review"],
  approve: ["review"],
  consolidationPlan: ["analysis"],
  savingsWhatIf: ["analysis"],
  overlap: ["analysis"],
  deliverableGenerate: ["generate"],
  deliverablePreview: ["quality-check"],
  deliverableRelease: ["approve-and-release"],
  recommendationsEmpty: ["recommendations"],
};

/** Whether `section` shows `block`. No section is the whole page, as before. */
export function showsBlock(
  section: SectionKey | undefined,
  block: TdBlock,
): boolean {
  return section === undefined || TD_BLOCK_SECTIONS[block].includes(section);
}

/** Sections that need a capability list, and say so when there is none. */
export const NEEDS_LIST: readonly SectionKey[] = [
  "overview",
  "ai-draft",
  "review",
  "analysis",
  "generate",
  "quality-check",
  "approve-and-release",
];

/**
 * The section header's visibility (plan v2, rule 6). Analysis mixes the two
 * states, so its header says "Client preview" and the what-if carries the
 * internal-only band. Approve and release says "Released to client" once the
 * deliverable is released; `TechDebtWorkspace` decides that from the data.
 */
export const TD_SECTION_VISIBILITY: Record<SectionKey, Visibility> = {
  overview: "internal",
  inputs: "internal",
  "ai-draft": "internal",
  review: "internal",
  analysis: "client-preview",
  generate: "internal",
  "quality-check": "client-preview",
  "approve-and-release": "client-preview",
  recommendations: "internal",
};

/** PENDING advisor approval, verbatim (#1376). */
export const TD_SECTION_COPY = {
  header: {
    overview: {
      purpose: "Where this Technical Debt Review stands and what to do next.",
      // "Go to the section the next step names" came out: nothing on Overview
      // links to a section (the progress stages are text), so it named a
      // control that does not exist (advisor, #736 6229125629).
      canDo: ["See the stage and the key figures for the current list"],
    },
    inputs: {
      purpose:
        "The client's inventory, which the capability list is built from.",
      canDo: [
        "Upload the inventory as a CSV or XLSX file",
        "Extract a capability list from an uploaded document",
        "Include or confirm the rows the extraction left out",
      ],
    },
    "ai-draft": {
      purpose: "Run the AI extraction and see what it produced.",
      canDo: [
        "Follow an extraction while it runs",
        "See how many uploaded rows became capabilities",
      ],
    },
    review: {
      purpose:
        "Check and correct the capability list row by row, then approve it.",
      canDo: [
        "Fix names, costs and categories, and split bundles",
        "Confirm or overturn each security classification",
        "Approve the list",
      ],
    },
    analysis: {
      purpose:
        "Explore overlaps and savings before the deliverable is generated.",
      canDo: [
        "See which tools do the same job, and what each overlap costs",
        "Try keep and cut decisions in the what-if",
      ],
    },
    generate: {
      purpose: "Produce the deliverable files from the approved list.",
      canDo: ["Finalize or re-finalize the deliverable", "Download the files"],
    },
    "quality-check": {
      purpose: "See what the client will get, before it is released.",
      canDo: ["Open the client dashboard preview"],
    },
    "approve-and-release": {
      purpose: "Release the finalized deliverable to the client.",
      canDo: ["Release the deliverable, after confirming"],
    },
    recommendations: {
      purpose:
        "This service's recommendations, for the conversation with the client.",
      canDo: ["See the recommendations, once they are built"],
    },
  } satisfies Record<SectionKey, { purpose: string; canDo: readonly string[] }>,
  /** The empty list, in a section: the upload is in Inputs, not "above". */
  noListDescription:
    "Upload an inventory in Inputs to run the first AI extraction.",
  recommendationsEmpty:
    "Recommendations are not built for Technical Debt Review yet.",
  /** Step 3's description, without its step numbers. */
  approveNote:
    "Records that the inventory was reviewed, so the deliverable is generated from rows a consultant signed off. Any later edit means approving again. Approving does not send anything to the client.",
  /** Step 4's blocked reasons, naming the section instead of "step 3". */
  generateBlockedDraft:
    "Approve the capability list in Review before generating a deliverable from it.",
  generateBlockedStale:
    "The list was edited after it was approved. Approve it again in Review before generating a deliverable from it.",
  /** #550's copy, naming Review instead of "step 2". */
  extractOutcomeUnknown:
    "We couldn't confirm whether the extraction finished. It may still complete and create a draft capability list. Reload the page later and check Review before extracting again. Extracting stays off on this page until you reload.",
  /** The deliverable-read failure, naming Generate instead of "the section below". */
  deliverableReadFailed:
    "Couldn't check for a finalized deliverable. What Generate shows is not a statement about whether one exists.",
  /** #640's re-check failure, without "step 4". */
  approvalRecheckFailed: (why: string) =>
    `Your edit was saved, but the approval state could not be re-checked (${why}). Reload the page before generating the deliverable.`,
  /** The reconciliation box sits in Inputs, not above the totals. */
  reconciliationTotals:
    "The totals in Overview and Review cover the included rows only, not the whole upload.",
  /** The result card (plan v2, rule 8), counted in uploaded rows. */
  result: {
    // Approved on #736 (6229125629) with one change: one row is singular, and
    // "is" follows a count of one.
    allIncluded: (asked: number) =>
      asked === 1
        ? "The 1 uploaded row is in the list."
        : `All ${asked} uploaded rows are in the list.`,
    someLeftOut: (applied: number, asked: number) =>
      `${applied} of ${asked} uploaded ${asked === 1 ? "row" : "rows"} ${applied === 1 ? "is" : "are"} in the list.`,
    leftOutReason: "Not in the list",
    // Only when some rows were left out. PENDING advisor approval, verbatim:
    // `nextOne`, the singular, which the approved line has no form for.
    next: "Check the list in Review. The rows left out are listed in Inputs.",
    nextOne: "Check the list in Review. The row left out is listed in Inputs.",
    // PENDING advisor approval, verbatim: a stored upload can have no rows (a
    // header-only file), which is not a success to count.
    noRows: "This upload had no rows, so there is nothing to count.",
    uncounted:
      "This result can't be counted: the AI could not match every capability to one uploaded row. Inputs shows what is known.",
    noRowCount:
      "This list has no record of how many rows were uploaded, so the result can't be counted.",
  },
  /** DeliverableCard's parts. */
  deliverable: {
    previewNone:
      "Finalize the deliverable in Generate to preview what the client will see.",
    releaseTitle: "Release to the client",
    releaseDescription:
      "Nothing reaches the client until you release it. Releasing is the point of no return.",
    releaseNone: "Finalize the deliverable in Generate before releasing it.",
  },
  /** IntakeDocumentsPanel's draft-source hint, naming Review. */
  draftSourceDiscardWhere: "in Review",
  /** ConsolidationPlanCard's description, naming the Review table. */
  planDescription:
    "Each row in the Review table carries a disposition: Keep, Cut, or Cut, covered by another tool. The annual costs of both kinds of cut add up to the estimated annual savings shown below. Finalize the deliverable when the dispositions are settled.",
} as const;
