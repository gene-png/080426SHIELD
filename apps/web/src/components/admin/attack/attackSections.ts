/**
 * #1377, the ATT&CK step of the UI section split: which section of the client
 * frame shows each block of `AttackWorkspace`, and the copy the sections add.
 * The table is the component map the PR body carries, so a test reads "every
 * block lands in exactly one section, except the ones listed" from here rather
 * than from prose.
 *
 * A block listed under more than one section is deliberate and says why in its
 * comment. Every other block is in exactly one.
 *
 * PENDING advisor approval, verbatim: every string in `ATTACK_SECTION_COPY`.
 * The section titles are Gene's tab names (`SECTIONS` labels), not new copy.
 */
import type { SectionKey } from "@/components/service-shell/SectionBar";
import type { Visibility } from "@/components/service-shell/SectionHeader";

export type AttackBlock =
  /** The assessment's status pill: a state the reader needs everywhere. */
  | "assessmentStatus"
  /** The failure bands (a refused action, a failed refresh, a failed load): a
   *  failure shows wherever the reader is, or it is invisible where it
   *  happened. */
  | "failures"
  /** Start assessment, Discard draft, Start revision. */
  | "lifecycle"
  | "revisionBanner"
  | "progressStages"
  | "noAssessment"
  | "aiInputs"
  | "runAi"
  | "aiPreview"
  | "runResult"
  | "runBlocked"
  | "scoring"
  | "computedReview"
  | "approve"
  | "staleDocs"
  | "outsideSubsetApproved"
  | "deliverableGenerate"
  | "deliverablePreview"
  | "deliverableRelease"
  | "heatmap"
  | "whatIf"
  | "messages"
  | "recommendationsEmpty";

const ALL: readonly SectionKey[] = [
  "overview",
  "inputs",
  "ai-draft",
  "review",
  "analysis",
  "generate",
  "quality-check",
  "approve-and-release",
];

export const ATTACK_BLOCK_SECTIONS: Record<AttackBlock, readonly SectionKey[]> =
  {
    assessmentStatus: ALL,
    failures: ALL,
    lifecycle: ["overview"],
    revisionBanner: ["overview"],
    progressStages: ["overview"],
    // The empty state is Overview's (its "Start assessment" is there); every
    // other section that needs an assessment points to it.
    noAssessment: ["overview"],
    aiInputs: ["inputs"],
    runAi: ["ai-draft"],
    aiPreview: ["ai-draft"],
    runResult: ["ai-draft"],
    runBlocked: ["ai-draft"],
    scoring: ["review"],
    // In TWO sections on purpose: the release refusal sends the consultant to
    // this panel, so it must be where that refusal is met (Approve and
    // release) as well as where the statuses are reviewed (Review).
    computedReview: ["review", "approve-and-release"],
    approve: ["review"],
    staleDocs: ["generate"],
    outsideSubsetApproved: ["generate"],
    deliverableGenerate: ["generate"],
    deliverablePreview: ["quality-check"],
    deliverableRelease: ["approve-and-release"],
    heatmap: ["analysis"],
    whatIf: ["analysis"],
    messages: ["overview"],
    recommendationsEmpty: ["recommendations"],
  };

/** Whether `section` shows `block`. No section is the whole page, as before. */
export function showsAttackBlock(
  section: SectionKey | undefined,
  block: AttackBlock,
): boolean {
  return (
    section === undefined || ATTACK_BLOCK_SECTIONS[block].includes(section)
  );
}

/** Sections that need an assessment, and say so when there is none. */
export const ATTACK_NEEDS_ASSESSMENT: readonly SectionKey[] = [
  "inputs",
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
 * deliverable is released; `AttackWorkspace` decides that from the data.
 */
export const ATTACK_SECTION_VISIBILITY: Record<SectionKey, Visibility> = {
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

/** PENDING advisor approval, verbatim (#1377). */
export const ATTACK_SECTION_COPY = {
  header: {
    overview: {
      purpose: "Where this ATT&CK coverage mapping stands and what to do next.",
      canDo: [
        "Start the assessment, or discard or revise it",
        "See the stage and message the client",
      ],
    },
    inputs: {
      purpose:
        "The security tools the AI may cite, and what it was not given, before a run.",
      canDo: ["See which tools are in scope and which are withheld"],
    },
    "ai-draft": {
      purpose: "Run the AI mapping and see what it produced.",
      canDo: [
        "Preview what will be sent to the AI",
        "Run the AI mapping",
        "See what a run covered and what it left out",
      ],
    },
    review: {
      purpose:
        "Check and correct the coverage of each technique, then approve the assessment.",
      canDo: [
        "Set each technique's status, tools and rationale",
        "Review the computed statuses that differ from the AI's",
        "Approve the assessment",
      ],
    },
    analysis: {
      purpose: "See the coverage rollup, and try changes in the what-if.",
      canDo: [
        "See coverage by tactic as the client will",
        "Try tool changes in the what-if",
      ],
    },
    generate: {
      purpose: "Produce the deliverable files from the approved assessment.",
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
      // Same string the advisor approved for Technical Debt (#736 6229792065).
      canDo: [
        "Nothing to do yet: this section is empty until recommendations are built.",
      ],
    },
  } satisfies Record<SectionKey, { purpose: string; canDo: readonly string[] }>,
  /** A section that needs an assessment, when there is none: the control is
   *  in Overview. */
  noAssessment: "Start the assessment in Overview to use this section.",
  recommendationsEmpty:
    "Recommendations are not built for MITRE ATT&CK Coverage Mapping yet.",
  /** Step 3's blocked reason, naming the section instead of "step 2". */
  approveBlockedNothingScored:
    "Nothing has been scored yet. Run the AI mapping in AI draft, or score techniques by hand in Review, first.",
  /** Step 4's blocked reason, naming the section instead of "step 3". */
  generateBlockedDraft:
    "Approve the assessment in Review before generating a deliverable from it.",
  /** The deliverable card's parts. */
  deliverable: {
    previewNone:
      "Finalize the deliverable in Generate to preview what the client will see.",
    releaseTitle: "Release to the client",
    releaseDescription:
      "Nothing reaches the client until you release it. Releasing is the point of no return.",
    releaseNone: "Finalize the deliverable in Generate before releasing it.",
  },
} as const;
