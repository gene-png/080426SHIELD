/**
 * #1378, the CSF half of the UI section split: which section of the client
 * frame shows each block of `CsfWorkspace` and `CsfPlaybookPanel`, and the
 * copy the sections add. The table is the component map the PR body carries,
 * so a test reads "every block lands in a section" from here, not from prose.
 *
 * A block listed under more than one section is deliberate and says why in
 * its comment. Every other block is in exactly one.
 *
 * PENDING advisor approval, verbatim: every string in `CSF_SECTION_COPY`. The
 * section titles are Gene's tab names (`SECTIONS` labels), not new copy.
 */
import type { SectionKey } from "@/components/service-shell/SectionBar";
import type { Visibility } from "@/components/service-shell/SectionHeader";

/** Every section a CSF service has: Inputs is folded into AI draft
 *  (`omittedSections`, plan v2 decision 1). */
const EVERY_SECTION: readonly SectionKey[] = [
  "overview",
  "ai-draft",
  "review",
  "analysis",
  "generate",
  "quality-check",
  "approve-and-release",
  "recommendations",
];

export type CsfBlock =
  /** The status pill and version: a state the reader needs in every section. */
  | "status"
  /** The refresh-failure band and the load-error card: a failed read shows
   *  wherever the reader is. */
  | "readFailures"
  | "revisionBanner"
  | "progressStages"
  | "discardDraft"
  | "startAssessment"
  | "startRevision"
  /** "Client self-assessment submitted. Review and edit ...": it points at
   *  Review's table and Approve. */
  | "submittedNote"
  | "aiSource"
  /** Seed, Run AI (with the offline guard), Preview what is sent, run status,
   *  the last-run note, run accounting and the provenance notice. */
  | "playbookRun"
  | "questionnaire"
  /** The playbook's retired-rows note, the coverage lines and the counts
   *  line: read with the table they describe. */
  | "playbookCoverage"
  | "playbookTable"
  | "exportPlaybook"
  | "dimensionEditor"
  | "approve"
  | "gapActions"
  | "gapList"
  | "staleDocs"
  | "deliverable"
  | "scoreCard"
  | "messages";

export const CSF_BLOCK_SECTIONS: Record<CsfBlock, readonly SectionKey[]> = {
  status: EVERY_SECTION,
  readFailures: EVERY_SECTION,
  revisionBanner: ["overview"],
  progressStages: ["overview"],
  discardDraft: ["overview"],
  startAssessment: ["overview"],
  startRevision: ["approve-and-release"],
  submittedNote: ["review"],
  aiSource: ["ai-draft"],
  playbookRun: ["ai-draft"],
  // The client's answers sit with the AI draft, which reads them (plan v2,
  // decision 1: Inputs folded into AI draft).
  questionnaire: ["ai-draft"],
  playbookCoverage: ["review"],
  playbookTable: ["review"],
  exportPlaybook: ["review"],
  dimensionEditor: ["review"],
  approve: ["review"],
  gapActions: ["analysis"],
  gapList: ["analysis"],
  staleDocs: ["generate"],
  // Finalize, downloads and Release are one card today; moving it whole keeps
  // its behaviour. Splitting Release into Approve and release is a question
  // for the advisor (issue #1378, question 1).
  deliverable: ["generate"],
  scoreCard: ["overview"],
  messages: ["overview"],
};

/** Whether `section` shows `block`. No section is the whole page, as before. */
export function showsCsfBlock(
  section: SectionKey | undefined,
  block: CsfBlock,
): boolean {
  return section === undefined || CSF_BLOCK_SECTIONS[block].includes(section);
}

/** Sections that need an assessment, and say so when there is none. */
export const CSF_NEEDS_ASSESSMENT: readonly SectionKey[] = [
  "ai-draft",
  "review",
  "analysis",
  "generate",
  "quality-check",
  "approve-and-release",
];

/**
 * The section header's visibility (plan v2, rule 6). Analysis mixes the two
 * states, so its header says "Client preview" as Tech Debt's does.
 */
export const CSF_SECTION_VISIBILITY: Record<SectionKey, Visibility> = {
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

/** PENDING advisor approval, verbatim (#1378). */
export const CSF_SECTION_COPY = {
  header: {
    overview: {
      purpose: "Where this NIST CSF 2.0 assessment stands and what to do next.",
      canDo: ["See the stage, the score and the open messages"],
    },
    // Never rendered: CSF has no Inputs section (`omittedSections`). The key
    // exists because the header table covers every `SectionKey`.
    inputs: {
      purpose: "The client's answers are collected in AI draft.",
      canDo: ["Open AI draft to see the client's answers"],
    },
    "ai-draft": {
      purpose: "The client's answers, and the AI draft built from them.",
      canDo: [
        "Seed the Working Profiles",
        "Run the AI draft",
        "Check or set a tier on a client answer",
      ],
    },
    review: {
      purpose: "Check every subcategory, correct it, then approve.",
      canDo: [
        "Read the Working Profile table",
        "Edit the dimension scores",
        "Approve the assessment",
      ],
    },
    analysis: {
      purpose: "See the gaps against the target tier and plan the actions.",
      canDo: ["Pick the target tier", "Record the action for a gap"],
    },
    generate: {
      purpose: "Produce the deliverable files from the approved assessment.",
      canDo: ["Finalize the deliverable", "Download the files"],
    },
    "quality-check": {
      purpose: "See what the client will get, before it is released.",
      canDo: ["Nothing to do here yet"],
    },
    "approve-and-release": {
      purpose: "Start a revision of a released assessment.",
      canDo: ["Start a revision"],
    },
    recommendations: {
      purpose: "This service's recommendations.",
      canDo: ["Nothing to do yet"],
    },
  } satisfies Record<SectionKey, { purpose: string; canDo: readonly string[] }>,
  /** No assessment yet, in a section: the Start control is in Overview. */
  noAssessmentDescription:
    "Start the assessment in Overview to use this section.",
  /** Step 4's blocked reason, naming the section instead of "step 3". */
  generateBlocked:
    "Approve the assessment in Review before generating a deliverable from it.",
} as const;
