/**
 * #1379, the Zero Trust split of the client frame's sections: which section
 * shows each block of `ZtWorkspace`, and the copy the sections add. The table
 * is the component map the PR body carries, so a test reads "every block lands
 * in a section" from here rather than from prose. It follows the Tech Debt
 * pilot (`techDebtSections.ts`, #1376).
 *
 * A block listed under more than one section is deliberate and says why in
 * its comment. Every other block is in exactly one.
 *
 * Zero Trust has no Inputs section (page-plan decision 1: Inputs is folded
 * into AI draft), so there is no `inputs` entry anywhere below.
 *
 * PENDING advisor approval, verbatim: every string in `ZT_SECTION_COPY`. The
 * section titles are Gene's tab names (`SECTIONS` labels), not new copy.
 */
import type { SectionKey } from "@/components/service-shell/SectionBar";
import type { Visibility } from "@/components/service-shell/SectionHeader";

/** The sections a Zero Trust service has (`omittedSections` in the frame). */
export type ZtSection = Exclude<SectionKey, "inputs">;

export type ZtBlock =
  /** The assessment's status pill: a state the reader needs in every section. */
  | "statusPill"
  /** "Start assessment", shown while there is no assessment. */
  | "startAssessment"
  /** "Discard draft" and "Start revision". */
  | "assessmentActions"
  /** The revision banner: a revision in progress shows wherever the reader is. */
  | "revisionBanner"
  | "progressStages"
  /** "Client self-assessment submitted": it tells the reader to approve the
   *  client's inputs, and the Approve control is in Review. */
  | "submittedBanner"
  /** The refresh-failure band and the load-error card: a failed read shows
   *  wherever the reader is. */
  | "readFailures"
  | "catalogLoading"
  | "runAi"
  | "aiRunStatus"
  | "runAccounting"
  | "questionnaire"
  | "approve"
  | "scoreCard"
  | "gapList"
  | "roadmap"
  | "messages"
  | "deliverableGenerate"
  | "deliverablePreview"
  | "deliverableRelease"
  | "recommendationsEmpty";

const ALL: readonly ZtSection[] = [
  "overview",
  "ai-draft",
  "review",
  "analysis",
  "generate",
  "quality-check",
  "approve-and-release",
];

export const ZT_BLOCK_SECTIONS: Record<ZtBlock, readonly ZtSection[]> = {
  statusPill: ALL,
  startAssessment: ["overview"],
  assessmentActions: ["overview"],
  revisionBanner: ALL,
  progressStages: ["overview"],
  submittedBanner: ["review"],
  readFailures: ALL,
  catalogLoading: ALL,
  // Run AI, the preview of what is sent, and the guard are all in AI draft.
  runAi: ["ai-draft"],
  aiRunStatus: ["ai-draft"],
  runAccounting: ["ai-draft"],
  questionnaire: ["review"],
  approve: ["review"],
  // The score and its per-pillar rollup are the key figures of the page.
  scoreCard: ["overview"],
  gapList: ["analysis"],
  roadmap: ["analysis"],
  // The message thread is the page's one channel with the client, not a step.
  messages: ["overview"],
  deliverableGenerate: ["generate"],
  deliverablePreview: ["quality-check"],
  deliverableRelease: ["approve-and-release"],
  recommendationsEmpty: ["recommendations"],
};

/** Whether `section` shows `block`. No section is the whole page, as before. */
export function showsBlock(
  section: SectionKey | undefined,
  block: ZtBlock,
): boolean {
  return (
    section === undefined ||
    (ZT_BLOCK_SECTIONS[block] as readonly SectionKey[]).includes(section)
  );
}

/**
 * The section header's visibility (plan v2, rule 6). Analysis and Quality
 * check show what the client will see, so they say "Client preview". Approve
 * and release says "Released to client" once the deliverable is released;
 * `ZtWorkspace` decides that from the data.
 */
export const ZT_SECTION_VISIBILITY: Record<ZtSection, Visibility> = {
  overview: "internal",
  "ai-draft": "internal",
  review: "internal",
  analysis: "client-preview",
  generate: "internal",
  "quality-check": "client-preview",
  "approve-and-release": "client-preview",
  recommendations: "internal",
};

/** PENDING advisor approval, verbatim (#1379). */
export const ZT_SECTION_COPY = {
  header: {
    overview: {
      purpose: "Where this Zero Trust assessment stands and what to do next.",
      canDo: [
        "Start the assessment, discard a draft, or start a revision",
        "See the stage, the score and the message thread",
      ],
    },
    "ai-draft": {
      purpose:
        "Have the AI suggest a maturity stage for each capability, and see what it produced.",
      canDo: [
        "Run the AI, or preview what would be sent",
        "See what the AI applied, left out or could not use",
      ],
    },
    review: {
      purpose:
        "Check every capability and set the maturity stage you can defend, then approve.",
      canDo: [
        "Set stages, notes and targets for each capability",
        "Approve the assessment, or the client's inputs",
      ],
    },
    analysis: {
      purpose:
        "See the gaps to the target stage and the roadmap, before the deliverable is generated.",
      canDo: ["Change the target stage and see the gaps move"],
    },
    generate: {
      purpose: "Produce the report files from the approved assessment.",
      canDo: ["Send for evaluation, or re-run it", "Download the files"],
    },
    "quality-check": {
      purpose: "See what the client will get, before it is released.",
      canDo: ["Open the client dashboard preview"],
    },
    "approve-and-release": {
      purpose: "Release the evaluated report to the client.",
      canDo: ["Release to the client, after confirming"],
    },
    recommendations: {
      purpose:
        "This service's recommendations, for the conversation with the client.",
      canDo: [
        "Nothing to do yet: this section is empty until recommendations are built.",
      ],
    },
  } satisfies Record<ZtSection, { purpose: string; canDo: readonly string[] }>,
  /** No assessment yet, in a section other than Overview. */
  noAssessmentDescription: "Start the assessment in Overview to begin scoring.",
  recommendationsEmpty:
    "Recommendations are not built for Zero Trust assessments yet.",
  /** The old step 3 description, naming Review instead of "step 3". */
  approveNote:
    "Locks the scoring so the deliverable is generated from a fixed set of answers. Approving does not send anything to the client.",
  /** The old step 4's blocked reason, naming the section instead of "step 3". */
  generateBlocked:
    "Approve the assessment in Review before generating a deliverable from it.",
  /** The submitted banner's last clause, naming Generate instead of "the deliverable section". */
  submittedBanner:
    "Review and edit their answers below for completeness and accuracy, then approve the client inputs and send for evaluation in Generate.",
  /** ZtDeliverableCard's parts. */
  deliverable: {
    previewNone:
      "Send the assessment for evaluation in Generate to preview what the client will see.",
    releaseTitle: "Release to the client",
    releaseDescription:
      "Nothing reaches the client until you release it. Releasing is the point of no return.",
    releaseNone:
      "Send the assessment for evaluation in Generate before releasing it.",
  },
} as const;
