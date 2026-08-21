"use client";

import * as React from "react";

import type { AttackRunAiResponse } from "@/lib/attack/types";

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

export function AttackCitationAccounting({
  result,
}: {
  result: AttackRunAiResponse;
}) {
  const confirmed = result.citations_confirmed ?? 0;
  const needsReview = result.citations_needs_review ?? 0;
  const rejected = result.citations_rejected ?? 0;
  const total = confirmed + needsReview + rejected;

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

  return (
    <div
      className="flex flex-col gap-1 text-sm"
      data-testid="attack-citation-accounting"
      aria-live="polite"
    >
      <p className="text-ink-secondary">
        {total === 1 ? "1 tool citation" : `${total} tool citations`} checked
        against the client&rsquo;s capability list:{" "}
        <span className="font-semibold text-ink-primary">{confirmed}</span>{" "}
        confirmed,{" "}
        <span className="font-semibold text-ink-primary">{needsReview}</span>{" "}
        need review,{" "}
        <span className="font-semibold text-ink-primary">{rejected}</span>{" "}
        rejected.
      </p>

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
    </div>
  );
}
