export interface RiskGate {
  unlocked: boolean;
  has_attack: boolean;
  has_csf: boolean;
  has_zt: boolean;
  /** ABSENT — no assessment of this kind exists. Remedy: create one. */
  missing: string[];
  /**
   * EXISTS but is not approved, so it cannot be synthesized into a register
   * that will be exported under the client's name (#237). Remedy: approve it.
   *
   * Separate from `missing` because the remedies differ, and a renderer that
   * joins them into one "first complete:" sentence tells a consultant to create
   * an assessment they already have. Optional so an older client parses a newer
   * response.
   */
  not_finalized?: string[];
  /**
   * What actually BLOCKS generation — the unlock rule restated over APPROVED
   * inputs. Distinct from `not_finalized`, which reports.
   *
   * A renderer must gate the "approve first" screen on THIS, not on
   * `not_finalized`: an unapproved input that is not required does not block,
   * and telling a consultant to approve it would send them to approve
   * unfinished work.
   */
  synthesizable_missing?: string[];
}

export interface RiskEntry {
  id: string;
  title: string;
  description: string | null;
  axis: string | null;
  source: string | null;
  source_id: string | null;
  linked_techniques: string[] | null;
  linked_controls: string[] | null;
  likelihood: string | null;
  impact: string | null;
  tier: string | null;
  compensating_controls: string | null;
  residual_risk: string | null;
  recommended_action: string | null;
  rationale: string | null;
  origin: string;
  trust: string | null;
  /**
   * What the model proposed for this entry's link fields and LOST (#132).
   *
   * THREE states, and treating it as two reinstates the defect the field was
   * added for:
   *
   *   `null` — the entry predates migration 0048. Not recorded; infer nothing.
   *   `{}`   — recorded, and nothing was dropped. A positive claim.
   *   `{...}` — `field -> [values]` the model sent that matched nothing in the
   *             client's own assessments.
   *
   * Without it, `linked_techniques: []` is identical whether the model
   * proposed nothing or proposed five things that all failed to resolve.
   *
   * Read by the Source column, which renders `not recognised` rather than the
   * em dash an absent source gets — without that, a DROPPED source and an
   * absent one are the same cell, which is this issue's own harm in the field
   * it newly validates (#132 review).
   */
  dropped_links: Record<string, string[]> | null;
}

export interface RiskRegister {
  /**
   * Inputs that EXISTED and were not approved, so they contributed nothing to
   * this register. Present and populated on the POST /generate response only.
   *
   * **`GET .../register/latest` always returns `[]`, and that is a limit rather
   * than a bug in this type.** Nothing about the exclusion is persisted, so a
   * read path cannot reconstruct it without a schema change -- tracked in #240.
   * The consequence is that the banner below survives until the page is
   * reloaded and no further, which the renderer says out loud rather than
   * implying durability it does not have.
   */
  excluded_inputs: string[];
  /**
   * #121's outcome counters.
   *
   * An entry stored with no tier renders as em dashes, is dropped from the 5x5
   * matrix, and is still counted by `total_entries` -- so a register can report
   * forty open risks whose matrix sums to fewer than forty with nothing saying
   * why. Two causes reach that state: a value the model supplied that would not
   * resolve, and a key it simply omitted. These count the OUTCOME, so they are
   * non-zero under either.
   *
   * Unlike `excluded_inputs` above, these are DERIVED server-side from the
   * stored entries rather than being a property of the generate call, so they
   * are correct on `GET .../register/latest` too and survive a reload.
   */
  entries_total: number;
  entries_without_tier: number;
  /**
   * #132, the same instrument pointed at the LINKS, and three counters because
   * there are three states.
   *
   * `entries_with_dropped_links` is what to look at; `entries_unlinked_after_drops`
   * is what the consultant SEES, an entry that proposed linkage and kept none
   * and so renders exactly like one nobody linked; `entries_links_not_recorded`
   * is the pre-0048 rows, so "nothing was dropped" and "nobody was counting"
   * stay apart.
   *
   * Derived server-side from the stored entries, like the two above, so they
   * are correct on `GET .../register/latest` and survive a reload. That is only
   * possible because the drop is persisted — a counter about the generate run
   * would read 0 here.
   */
  entries_with_dropped_links: number;
  entries_unlinked_after_drops: number;
  entries_links_not_recorded: number;
  id: string;
  client_id: string;
  version: number;
  generated_by: string | null;
  finalized_at: string | null;
  created_at: string;
  xlsx_artifact_id: string | null;
  pdf_artifact_id: string | null;
  docx_artifact_id: string | null;
  xlsx_filename: string | null;
  pdf_filename: string | null;
  docx_filename: string | null;
  entries: RiskEntry[];
  tier_counts: Record<string, number>;
  axis_counts: Record<string, number>;
  action_counts: Record<string, number>;
}
