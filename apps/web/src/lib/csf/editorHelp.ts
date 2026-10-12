/**
 * C-2 (#1056): the instructions on CSF "Edit dimension scores", approved
 * verbatim by the advisor (#736, 6115345112). Plain strings, no logic; the
 * test types its own copies of them rather than importing these.
 *
 * WHAT EACH ONE RESTS ON. Every number here equals what the engine computes,
 * and both are pinned to the spec (reference-docs/SHIELDv2_Master_Spec.txt,
 * "Mapped to Maturity Level 1-5" and "Evidence rule"):
 * - the 0..2 scale and the 0..10 total: `DimensionScores.clamped` and `total`
 *   in apps/api/app/csf/playbook.py;
 * - the level bands: `maturity_level` ("0-2 -> L1, 3-5 -> L2, 6-7 -> L3,
 *   8-9 -> L4, 10 -> L5");
 * - the evidence cap: `score_tier` (Implementation at most 1, level at most 2);
 * - "Run AI never ticks this box": `_RUN_FIELDS` in apps/api/app/routes/csf.py
 *   is the five dimensions and `what_we_found`, and only
 *   `patch_dimension_score` writes `has_evidence`. If Gene rules that the
 *   client's attached evidence should count (#736, 6115345112), H3 changes;
 * - Target and In scope: `enterprise_subcategories` in
 *   apps/api/app/csf/enterprise.py (`max(targets)`, `is_gap`, and
 *   `if not r.in_scope: continue`);
 * - Lock: the `locked` skip in `_apply_suggestions`; the PATCH has no lock
 *   check.
 *
 * DRIFT GUARD for DIMENSION_HINTS and RUBRIC_ROWS: they paraphrase section 6
 * ("Dimension-specific rubric") of `_CSF_SCORE_PROMPT` in
 * apps/api/app/ai/jobs.py, whose length and sha256 are pinned by
 * apps/api/tests/unit/test_csf_score_prompt.py. When that pin changes, re-read
 * section 6 against these two and bring any wording change to the advisor.
 */

export const HELP_SUMMARY = "How to score a row";

export const HELP_SCALE =
  "Score each of the five dimensions 0, 1 or 2 for this subcategory, for the systems in the selected impact tier. 0 means not demonstrated, 1 means partial or informal, and 2 means established: formal, consistently performed, and applied across the tier's systems. When a score is between two values, choose the lower one unless the notes or evidence show the higher one is met. These are the same definitions Run AI is told to use.";

export const HELP_LEVELS_INTRO =
  "The five scores add up to a total from 0 to 10, and the total sets the maturity level:";

export const HELP_LEVEL_BANDS: readonly string[] = [
  "0 to 2: L1",
  "3 to 5: L2",
  "6 to 7: L3",
  "8 to 9: L4",
  "10: L5",
];

export const HELP_EVIDENCE =
  'Tick "Evidence on file" only when evidence for this subcategory and tier is held. Without it, Implementation counts as no more than 1 and the level cannot exceed L2, whatever the scores. Run AI never ticks this box, and a file the client attached to the questionnaire does not tick it either: a consultant has to.';

export const HELP_TARGET =
  'Target is the level the client should reach for this subcategory in this tier. The Enterprise profile compares its rolled-up level, usually the lowest of the in-scope tiers, with the highest target set on any in-scope tier. Below the target is a gap. With no target on any in-scope tier, the subcategory is not checked for a gap: it is counted as "with no target", not as met.';

export const HELP_IN_SCOPE =
  'Untick "In scope" when this subcategory does not apply to the systems in this tier. An out-of-scope row is left out of the Enterprise level, the gaps and their priorities. If every tier is out of scope, the subcategory leaves the Enterprise profile.';

export const HELP_LOCK =
  '"Lock vs AI reruns" stops Run AI from changing this row\'s scores and findings. You can still edit a locked row yourself. Without a lock, a later live Run AI can replace scores you entered. Edits are paused while a run is in progress.';

export type DimKey =
  "governance" | "policy" | "implementation" | "monitoring" | "improvement";

/** D1-D5: one line under each dimension, read as its radiogroup's description. */
export const DIMENSION_HINTS: Readonly<Record<DimKey, string>> = {
  governance:
    "Ownership, accountability, authority and oversight for this outcome.",
  policy:
    "A documented, approved and followed policy, process, plan or procedure.",
  implementation:
    "The outcome is actually performed. Planned or documented-only scores 0.",
  monitoring:
    "Monitoring, testing or review on a defined cadence. Logging alone is not monitoring.",
  improvement:
    "A recurring cycle that uses lessons learned and findings to improve. One fix is not a cycle.",
};

export const RUBRIC_HEADERS: readonly string[] = ["Dimension", "0", "1", "2"];

/** The 0/1/2 rubric, one row per dimension: [label, 0, 1, 2]. */
export const RUBRIC_ROWS: readonly (readonly [
  string,
  string,
  string,
  string,
])[] = [
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

/**
 * S1: beside "(capped — no evidence)", only on a capped row. "No more than 1"
 * because `score_tier` caps on two paths: the Implementation clamp, and the
 * level clamp alone on a row whose Implementation is already 0 or 1 (#1076).
 */
export const CAPPED_NOTE =
  "Without evidence, Implementation counts as no more than 1 in the total, and the level cannot go above L2.";

/**
 * S2: under Target, only when this tier's row has none. The gap is judged per
 * subcategory against the highest target on any in-scope tier
 * (`enterprise_subcategories`: `max(targets)`), so an untargeted tier is still
 * checked when another tier has a target (#1076).
 */
export const NO_TARGET_NOTE =
  "No target on this tier. The subcategory is still checked for a gap if another in-scope tier has a target.";
