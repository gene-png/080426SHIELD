"use client";

import * as React from "react";

import type {
  AttackOmittedTechnique,
  AttackRunAiResponse,
} from "@/lib/attack/types";

import { statusLabel } from "./StatusBadge";

/**
 * #806 C4 (PR #951 review, F2): the run refuses an AI Partial whose reason only
 * a consultant may give, and the row keeps the status it had. Said here so a
 * row the new prompt disputed is not read as one the AI agreed with.
 *
 * Copy approved verbatim, singular and plural (advisor, #736 comment
 * 6068587667). Both forms live here so a later ruling is a one-line change.
 *
 * D-076, the remedy it names exists today: the technique panel's `ReasonField`
 * select offers every catalogue reason for the row's status
 * (`reasonCodes.filter((r) => r.status === status)`, fed `catalog.reason_codes`
 * by `AttackWorkspace`), and the PATCH accepts any reason `is_valid_reason`
 * gives that status, so a consultant can set all seven Partial reasons. Only
 * the Run-AI apply loop refuses the four (`_AI_FORBIDDEN_PARTIAL_REASONS`).
 */
export const FORBIDDEN_REASON_REFUSED_COPY = {
  one: "1 technique was suggested as Partial with a reason only a consultant can give, so it was not applied and keeps the status it had. A consultant can set that reason in the technique panel.",
  many: (n: number) =>
    `${n} techniques were suggested as Partial with a reason only a consultant can give, so they were not applied and keep the status they had. A consultant can set that reason in the technique panel.`,
} as const;

/**
 * What happened to the tools the model cited (W2).
 *
 * Before the resolver, a cited name that missed the capability list by a word
 * was dropped SILENTLY — no count, no reason. The technique kept whatever status
 * the model gave it, so it either read as a `gap` on a control the client owns,
 * or as `covered` with an empty tool list. A fabricated gap is the failure N-033
 * shipped, 607 of them.
 *
 * Three outcomes, and they are deliberately not weighted the same:
 *
 * - **confirmed** is the normal case and gets no emphasis. Shouting about the
 *   common path is how a real warning gets trained away (#31).
 * - **needs review** is APPLIED and visible. The resolver had to change or
 *   assume something, and inference is not confirmation however plausible.
 * - **rejected** is gone, and quoted VERBATIM: "Tenable io" tells a consultant
 *   the list holds "Tenable.io". A bare count tells them nothing to act on.
 *
 * The line renders on a clean run too, so its absence never reads as zero.
 *
 * SCOPE, and the copy has to carry it because nothing else does. `run_ai`
 * assigns the technique's STATUS from the model independently of what happens
 * to its citations. So a technique whose every citation was rejected keeps the
 * status the model gave it — typically `covered` — with an EMPTY tool list, and
 * still counts in full toward `coverage_pct` and the client PDF.
 *
 * An earlier version of this file told the consultant the opposite: "A technique
 * whose only evidence was dropped now reads as uncovered." That was the inverse
 * of the truth, and it understated the harm — the real risk is coverage
 * OVERSTATED with nothing behind it, which is the failure the resolver's own
 * module docstring names. 5.1's `pending_review` enforcement is the fix and is
 * not in W2.
 */

const ITEM_CAP = 10;

function joinCapped(items: string[]): string {
  const shown = items.slice(0, ITEM_CAP).join(", ");
  const rest = items.length - ITEM_CAP;
  return rest > 0 ? `${shown}, and ${rest} more` : shown;
}

type KeptTechnique = AttackOmittedTechnique & {
  kept_status: NonNullable<AttackOmittedTechnique["kept_status"]>;
};

/**
 * One group of omitted techniques, at most `ITEM_CAP`, then "and {rest} more"
 * (A2's approved wording, used for A3 too). Per group: each group's heading
 * already states its full count.
 */
function OmittedItems<T extends AttackOmittedTechnique>({
  items,
  describe,
}: {
  items: T[];
  describe: (t: T) => string;
}) {
  const rest = items.length - ITEM_CAP;
  return (
    <ul className="list-disc pl-5">
      {items.slice(0, ITEM_CAP).map((t) => (
        <li key={t.technique_code}>{describe(t)}</li>
      ))}
      {rest > 0 ? <li>and {rest} more</li> : null}
    </ul>
  );
}

/**
 * #853: the techniques a SUCCESSFUL batch was asked about and that no entry
 * named. Copy A1 to A4 approved verbatim (#736 comment 6090870696); the twins
 * are ZT's `ZtOmittedBlock` (#840) and CSF's playbook panel (#836).
 *
 * Not a refusal: an entry that names a technique and is refused is an answer,
 * not an omission. One exception since #1047: a technique the first pass left
 * out whose RE-ASK answer is refused stays here (nothing applied it), so it
 * can be counted both here and on the N/A or forbidden-reason line below; each
 * line is true of it, and they are not to be added up. Only the N/A and
 * forbidden-reason refusals are counted in
 * this panel, on their own lines further down (`not_applicable_refused`,
 * `forbidden_reason_refused`); the rest are only in the audit row's `details`
 * and reach no screen (#859). A failed batch's techniques are the failed-batch
 * alert's, which is why this block sits directly after it.
 *
 * A2 (no status before the run) is neutral: the technique stays unscored and
 * reads as unscored everywhere. A3 (a status kept) is danger and carries A4,
 * because that status was not confirmed by this run and still reaches the
 * coverage figures and the deliverable. A3 and A4 share one region: an alert
 * when it is the panel's only alert, a polite `status` beside another, so two
 * assertive regions never announce over each other.
 *
 * A4's remedies exist today (D-076): Run AI in `AttackWorkspace`, and the
 * technique panel's status control.
 *
 * Absent (a run stored before #853) or 0 renders nothing.
 */
function AttackOmittedBlock({
  result,
  otherAlert,
}: {
  result: AttackRunAiResponse;
  otherAlert: boolean;
}) {
  const n = result.omitted_count ?? 0;
  if (n === 0) return null;
  const items = result.omitted_techniques ?? [];
  const unscored = items.filter((t) => t.kept_status === null);
  const kept = items.filter((t): t is KeptTechnique => t.kept_status !== null);
  return (
    <div className="flex flex-col gap-1" data-testid="attack-omitted">
      <p className="text-ink-secondary" data-testid="attack-omitted-count">
        {n === 1
          ? "1 technique got no status from the AI this run."
          : `${n} techniques got no status from the AI this run.`}
      </p>
      {unscored.length > 0 ? (
        <div
          className="text-ink-secondary"
          data-testid="attack-omitted-unscored"
        >
          <p>
            No status before this run, so still unscored ({unscored.length}):
          </p>
          <OmittedItems items={unscored} describe={(t) => t.technique_code} />
        </div>
      ) : null}
      {kept.length > 0 ? (
        <div
          className="flex flex-col gap-1 text-status-danger-fg"
          role={otherAlert ? "status" : "alert"}
          data-testid="attack-omitted-kept"
        >
          <div data-testid="attack-omitted-kept-list">
            <p>Kept the status it had ({kept.length}):</p>
            <OmittedItems
              items={kept}
              describe={(t) =>
                `${t.technique_code} (${statusLabel(t.kept_status)})`
              }
            />
          </div>
          <p data-testid="attack-omitted-check">
            Check these before approving. A status kept this way was not
            confirmed by this run and reaches the coverage figures and the
            deliverable as it is. Run AI again, or set the status in the
            technique panel.
          </p>
        </div>
      ) : null}
    </div>
  );
}

/**
 * #1047: the run asked a second time about the techniques a successful batch
 * left out. The omitted block above already counts what is STILL missing
 * after that; this line says the second ask happened, and how many of its
 * requests failed. Copy R-1047-1, approved verbatim (#736 comment 6206422365),
 * counts comma-formatted.
 *
 * Absent (a run stored before #1047) or 0 renders nothing.
 */
function AttackReaskLine({ result }: { result: AttackRunAiResponse }) {
  const asked = result.reasked_count ?? 0;
  if (asked === 0) return null;
  const total = result.reask_batches_total ?? 0;
  const failed = result.reask_batches_failed ?? 0;
  const count = (n: number) => n.toLocaleString("en-US");
  return (
    <p className="text-ink-secondary" data-testid="attack-reask">
      {asked === 1
        ? "1 technique the AI left out was asked about again."
        : `${count(asked)} techniques the AI left out were asked about again.`}
      {failed > 0
        ? ` ${count(failed)} of ${count(total)} of those follow-up requests failed, so those techniques are still listed above as left out.`
        : null}
    </p>
  );
}

/**
 * #1181: Gene's plain-English citation line, replacing the numeric headline
 * ("{n} tool citations checked against the client's capability list: ...").
 * Copy C-1 to C-5 approved verbatim (#736 comment 6216024281, from the
 * proposal in 6208173127); counts comma-formatted. C-2a and C-5a keep #115's
 * "completed batches only" qualifier on a partial run, and the singulars at
 * n = 1 are 6219475831 item 5.
 */
const CITATION_INTRO =
  "For each attack technique, the AI listed which of the client's tools help stop it, spot it or respond to it. Each time it named a tool, we checked that the tool is really on the client's approved list, so the AI can't make one up.";

function citationLine(
  confirmed: number,
  needsReview: number,
  rejected: number,
  runIncomplete: boolean,
): string {
  const n = (k: number) => k.toLocaleString("en-US");
  const total = confirmed + needsReview + rejected;
  if (total === 0) {
    // C-5a (advisor, #736 6219475831 item 5): a partial run keeps #115's
    // qualifier here too -- the failed batches may have named tools.
    return runIncomplete
      ? `${CITATION_INTRO} The AI named no tools in the completed batches, so there was nothing to check.`
      : `${CITATION_INTRO} The AI named no tools, so there was nothing to check.`;
  }
  const checked = runIncomplete
    ? `We checked ${n(total)} of these, from the batches that completed.`
    : `We checked ${n(total)} of these.`;
  if (needsReview === 0 && rejected === 0) {
    // The singular is 6219475831 item 5's "It is on the list.".
    const all =
      total === 1 ? "It is on the list." : `All ${n(total)} are on the list.`;
    return `${CITATION_INTRO} ${checked} ${all} None need a closer look and none were rejected.`;
  }
  const onList =
    confirmed === 0
      ? "None are on the list."
      : `${n(confirmed)} are on the list.`;
  const closer =
    needsReview === 0
      ? "None need a closer look."
      : `${n(needsReview)} need a closer look.`;
  const gone =
    rejected === 0
      ? "None were rejected."
      : rejected === 1
        ? "1 was rejected."
        : `${n(rejected)} were rejected.`;
  return `${CITATION_INTRO} ${checked} ${onList} ${closer} ${gone}`;
}

export function AttackCitationAccounting({
  result,
}: {
  result: AttackRunAiResponse;
}) {
  const confirmed = result.citations_confirmed ?? 0;
  const needsReview = result.citations_needs_review ?? 0;
  const rejected = result.citations_rejected ?? 0;

  // A payload from before the resolver carries none of these. Rendering
  // "0 citations" over it would assert something the run never measured.
  if (
    result.citations_confirmed === undefined &&
    result.citations_needs_review === undefined &&
    result.citations_rejected === undefined
  ) {
    return null;
  }

  const reviewTools = result.citations_needs_review_tools ?? [];
  // The nullable-vendor case, called out separately. A vendor guess made against
  // a list with missing vendors is a different risk from a punctuation rescue,
  // and reporting them identically is what made that guard inert.
  const vendorGuesses =
    result.citations_needs_review_by_reason?.incomplete_vendor_data ?? [];
  const unusable = result.citations_unusable ?? 0;
  const rejectedExamples = result.citations_rejected_examples ?? [];
  // Rows, not citations. `needsReview` counts CITATIONS and a consultant works
  // through TECHNIQUES: one flagged tool cited by forty techniques is one number
  // above and forty pieces of work here.
  const pendingRows = result.pending_review_rows ?? 0;

  // #115. `mitre_map` runs as concurrent batches; a batch that raises is
  // counted and the run CONTINUES, and only a total failure raises. So a
  // partial run returns HTTP 200 and every count below is accumulated over the
  // batches that came back -- while the copy said "checked against the
  // client's capability list", full stop.
  //
  // `undefined` is not zero: a payload from before batching measured nothing
  // about it, and rendering "0 of 0 failed" over one would assert a clean run
  // that was never established.
  const batchesTotal = result.batches_total;
  const batchesFailed = result.batches_failed;
  // FAIL CLOSED on mixed presence.
  //
  // A first version required BOTH fields, so `batches_failed: 6` arriving
  // without `batches_total` suppressed the alert AND reverted the headline to
  // its unqualified form -- the guard written to close #115 reproducing #115
  // on that input. Absence must not resolve to "clean run": missing data
  // defaults to UNCONFIRMED, never to confirmed.
  //
  // So the trigger is the failure counter alone. `batches_total` is only used
  // to say "6 of 26" rather than "6", and its absence degrades the sentence
  // rather than the decision.
  const runIncomplete = (batchesFailed ?? 0) > 0;

  return (
    <div
      className="flex flex-col gap-1 text-sm"
      data-testid="attack-citation-accounting"
      aria-live="polite"
    >
      <p className="text-ink-secondary" data-testid="attack-citation-line">
        {citationLine(confirmed, needsReview, rejected, runIncomplete)}
      </p>

      {runIncomplete ? (
        <p
          className="text-status-danger-fg"
          role="alert"
          data-testid="attack-run-incomplete"
        >
          <span className="font-semibold">
            {batchesTotal === undefined
              ? `${batchesFailed} batches failed`
              : `${batchesFailed} of ${batchesTotal} batches failed`}
          </span>
          , so their techniques were not mapped and nothing below covers them. A
          batch can fail after the model answered &mdash; a malformed response
          is refused on arrival &mdash; so check the AI spend for this run
          rather than assuming nothing was sent. Re-run before relying on this
          draft. On a re-run over an assessment that was already scored, the
          techniques a failed batch missed keep the statuses they had, so the
          matrix will look complete either way &mdash; this line is the only
          place that says otherwise.
        </p>
      ) : null}

      {/* #853, directly after the failed-batch alert: that alert covers the
          techniques of the batches that failed, this block those of the
          batches that answered. The rejected-citations alert below is the
          other assertive region this one must not shout over. */}
      <AttackOmittedBlock
        result={result}
        otherAlert={runIncomplete || rejected > 0}
      />
      <AttackReaskLine result={result} />

      {pendingRows > 0 ? (
        <p
          className="text-status-warning-fg"
          data-testid="attack-citations-pending"
        >
          {pendingRows === 1
            ? "1 technique is held out of the coverage score"
            : `${pendingRows} techniques are held out of the coverage score`}{" "}
          until their evidence is confirmed. Coverage % is a ratio over the
          techniques that can be claimed right now, so it is reported beside a
          pending-review count rather than on its own. Open a flagged technique
          in the matrix below to see what was cited and confirm it.
        </p>
      ) : null}

      {needsReview > 0 ? (
        <p
          className="text-status-warning-fg"
          data-testid="attack-citations-review"
        >
          Applied, but the name had to be resolved rather than matched
          {reviewTools.length > 0 ? `: ${joinCapped(reviewTools)}` : ""}. Until
          someone confirms them, every technique whose only evidence is one of
          these is held out of the coverage score — reported as pending review,
          not as a gap.
          {vendorGuesses.length > 0 ? (
            <>
              {" "}
              <span className="font-semibold">
                {joinCapped(vendorGuesses)}
              </span>{" "}
              {vendorGuesses.length === 1 ? "was" : "were"} matched on a vendor
              name while other tools on the list have no vendor recorded — the
              riskiest of these, because the list cannot rule out that one of
              those belongs to the same vendor.
            </>
          ) : null}
        </p>
      ) : null}

      {rejected > 0 ? (
        <p
          className="text-status-danger-fg"
          role="alert"
          data-testid="attack-citations-rejected"
        >
          {rejected === 1
            ? "1 citation named a tool that is not on the list and was dropped"
            : `${rejected} citations named tools that are not on the list and were dropped`}
          {rejectedExamples.length > 0
            ? `, e.g. ${joinCapped(rejectedExamples)}`
            : ""}
          . The technique keeps whatever status the model gave it — clearing the
          citation has to be able to put it back — but with nothing left behind
          that status, it is held out of the coverage score as pending review
          rather than counted as covered.
        </p>
      ) : null}

      {/* #109. A run can DECLINE to write a row's citation record: when the
          column is NULL and a field this run did not resolve still holds tools,
          the write is skipped so the row stays withheld. That is fail-closed on
          score and was completely silent -- the consultant saw a row the run had
          just touched, unchanged, with nothing saying the run had looked at it
          and stopped. Every other count in this component reaches a surface;
          this one shipped reaching none, which reads as an oversight rather
          than a decision. */}
      {(result.rows_left_unresolved ?? 0) > 0 ? (
        <p
          className="text-ink-secondary"
          data-testid="attack-rows-left-unresolved"
        >
          {result.rows_left_unresolved === 1
            ? "1 technique was left unresolved"
            : `${result.rows_left_unresolved} techniques were left unresolved`}{" "}
          because a field this run did not answer still holds tools nothing has
          checked
          {(result.unresolved_fields ?? []).length > 0
            ? ` (${(result.unresolved_fields ?? []).join(", ")})`
            : ""}
          {/* #683: the rest of the sentence agrees with the counts above it --
              "1 technique was" followed by "They ... their tools". */}
          {`. ${result.rows_left_unresolved === 1 ? "It stays" : "They stay"} held out of the coverage score. Re-run so the model answers ${(result.unresolved_fields ?? []).length === 1 ? "that field" : "those fields"}, or set ${result.rows_left_unresolved === 1 ? "its" : "their"} tools yourself.`}
        </p>
      ) : null}

      {unusable > 0 ? (
        <p
          className="text-ink-secondary"
          data-testid="attack-citations-unusable"
        >
          {unusable === 1
            ? "1 entry was not a usable tool name"
            : `${unusable} entries were not usable tool names`}{" "}
          (the model sent the wrong shape). Those tool lists were overwritten
          with nothing — re-run before relying on this draft.
        </p>
      ) : null}

      {/* #645. An edit that checked the run's lock before the run existed can
          land after it started. The run keeps that edit rather than overwrite
          it, and says how many it kept, so a row the run "skipped" is not
          mistaken for one it looked at and agreed with. */}
      {(result.rows_skipped_edited ?? 0) > 0 ? (
        <p
          className="text-ink-secondary"
          data-testid="attack-rows-skipped-edited"
        >
          {result.rows_skipped_edited === 1
            ? "1 technique was edited after this run started, so the run left it as edited"
            : `${result.rows_skipped_edited} techniques were edited after this run started, so the run left them as edited`}
          .
        </p>
      ) : null}

      {/* #841. Only a consultant may rule a technique N/A, so the run refused
          every N/A the AI suggested. Said here so a refusal is not mistaken for
          the AI having no view on that technique. Copy approved verbatim
          (issue 841, comment 5983735013). */}
      {(result.not_applicable_refused ?? 0) > 0 ? (
        <p
          className="text-ink-secondary"
          data-testid="attack-not-applicable-refused"
        >
          {result.not_applicable_refused === 1
            ? "1 technique was suggested as N/A and not applied. Only a consultant can mark a technique N/A, in the technique panel."
            : `${result.not_applicable_refused} techniques were suggested as N/A and not applied. Only a consultant can mark a technique N/A, in the technique panel.`}
        </p>
      ) : null}

      {(result.forbidden_reason_refused ?? 0) > 0 ? (
        <p
          className="text-ink-secondary"
          data-testid="attack-forbidden-reason-refused"
        >
          {result.forbidden_reason_refused === 1
            ? FORBIDDEN_REASON_REFUSED_COPY.one
            : FORBIDDEN_REASON_REFUSED_COPY.many(
                result.forbidden_reason_refused ?? 0,
              )}
        </p>
      ) : null}
    </div>
  );
}
