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

/**
 * #403. How much of one assessment was SCORED, and therefore citable.
 *
 * `scored` is the size of that service's synthesis allow-list; `total` is the
 * rows the assessment holds. `total - scored` is what was left out for carrying
 * no consultant judgement.
 *
 * Both travel together because a count of what was excluded is not
 * self-describing without the population it came out of — the same reason a
 * percentage over a withheld population renders its withheld count beside it.
 */
export interface LinkScopeDisclosure {
  service: string;
  scored: number;
  total: number;
}

export interface RiskRegister {
  /**
   * Inputs that EXISTED and were not approved, so they contributed nothing to
   * this register. Carried on EVERY response that returns a register --
   * generate, latest and export alike.
   *
   * **[2026-09-11, #244] This used to say `GET .../register/latest` always
   * returns `[]`, because nothing was persisted and a read path "cannot
   * reconstruct it without a schema change -- tracked in #240".** The schema
   * change landed (migration 0047 stores the set in
   * `risk_registers.provenance`); only the read-back was missing, and
   * `_serialize` now does it. Every response carries the same set, so the
   * banner survives a reload.
   *
   * The note is kept rather than deleted because the OLD text is what a reader
   * would otherwise act on: it reads as a live limitation, and the remedy it
   * points at had already shipped.
   */
  excluded_inputs: string[];
  /**
   * Whether `excluded_inputs` is an answer or a silence.
   *
   * `false` means the register predates provenance recording, so nothing on
   * file says what was left out. An empty `excluded_inputs` cannot express
   * that, and reading it as "nothing was excluded" would be a false assurance
   * about the one population nobody can check.
   */
  excluded_inputs_recorded: boolean;
  /**
   * #121's outcome counters.
   *
   * An entry stored with no tier renders as em dashes, is dropped from the 5x5
   * matrix, and is still counted by `entries_total` -- so a register can report
   * forty open risks whose matrix sums to fewer than forty with nothing saying
   * why. Two causes reach that state: a value the model supplied that would not
   * resolve, and a key it simply omitted. These count the OUTCOME, so they are
   * non-zero under either.
   *
   * DERIVED server-side from the stored entries rather than being a property
   * of the generate call, so they are correct on `GET .../register/latest` too
   * and survive a reload.
   *
   * This used to open "Unlike `excluded_inputs` above" — which asserted, by
   * CONTRAST, the three things the docblock above now denies. That is how it
   * survived a sweep: it never says "not persisted", so a grep phrased around
   * the claim's own vocabulary misses it. `excluded_inputs` is persisted and
   * derived now too.
   */
  entries_total: number;
  /**
   * A partial synthesis KEEPS what succeeded (#372). `risk_synthesize` runs
   * concurrent batches, and a failed one costs its entries silently -- the
   * register renders short with nothing saying so.
   *
   * `| null`, NOT `?: number`, and the first revision of this field had it the
   * other way. The tally is PERSISTED in the register's provenance and read
   * back by `_serialize`, so every path -- generate, export, latest -- reports
   * the run the register came from. `null` means the register predates that
   * and nobody counted; it is NOT "nothing failed", and the two must stay
   * distinguishable or a reload reads as an all-clear.
   *
   * The wire really does carry `null`: no `exclude_none` or
   * `response_model_exclude_none` exists anywhere in `apps/api` (measured), so
   * FastAPI serialises the key. `?: number` declared a shape the server never
   * produces, and a presence test against it could never discriminate.
   */
  batches_total: number | null;
  batches_failed: number | null;

  /**
   * #330. The generate loop's INTENDED tally.
   *
   * `entries_total` is the TABLE read-back. The two shared a name for a while
   * and are not the same quantity -- they agree on every run any current
   * writer can produce, and diverge where a row is lost between `db.add` and
   * the flush.
   *
   * `| null`, NOT `?: number`, because that is what the wire carries. No
   * `exclude_none` exists anywhere in `apps/api` -- measured -- so FastAPI
   * serialises `"entries_intended": null` for every register predating the
   * field. The optional form declared a value that cannot arrive, and the
   * guard reading it (`!== undefined`) therefore never discriminated: the
   * banner stayed silent only because `null > n` coerces to false, an
   * implicit coercion nobody wrote down carrying the whole pre-#330
   * disclosure. Every sibling nullable on this interface is `| null`.
   *
   * `null` is "nobody counted" and renders no banner; a value ABOVE
   * `entries_total` is the loss. A value BELOW is impossible -- one writer
   * creates `RiskEntry` rows and nothing deletes them.
   */
  entries_intended: number | null;
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
  /**
   * #403. WHY the links are sparse, which the three counters above cannot say.
   *
   * Those three describe what the MODEL got wrong. This describes what the
   * ASSESSMENT does not contain: the synthesis allow-lists are now the codes a
   * client's assessments actually SCORED, so a client who scored 12 of 700
   * techniques gets links drawn from 12. Sparse linkage is then CORRECT and
   * reads as a regression, and the register has to say which it is.
   *
   * The two have OPPOSITE remedies, which is why they are separate fields
   * rather than one blended count: a dropped value is the model's fault and
   * regenerating may fix it; an unscored control is unfinished assessment work
   * and regenerating cannot. Telling a consultant to regenerate over the
   * second spends a live LLM call and returns the same sparse register.
   *
   * Persisted at generate into the provenance blob and read back, so it
   * survives a reload — the half #316 shipped without.
   */
  excluded_unscored_links: LinkScopeDisclosure[];
  /**
   * Whether `excluded_unscored_links` is an ANSWER or a SILENCE.
   *
   * `false` means the register predates the recording, so nothing on file says
   * how much of each assessment was scored. NOT the same fact as "everything
   * was scored", and an empty array cannot tell them apart — the same two-state
   * trap `excluded_inputs_recorded` exists for.
   */
  excluded_unscored_links_recorded: boolean;
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
