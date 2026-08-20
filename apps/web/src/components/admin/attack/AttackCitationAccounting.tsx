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
 * SCOPE, stated because a surfaced number that implies more than it does is the
 * defect this codebase keeps fixing: flagging a citation does NOT currently
 * change the coverage score. 5.1's rule — that unconfirmed support must not
 * feed the computed number — is enforced on the technique STATUS in
 * `analytics.py` and is not part of W2. The copy says so rather than letting a
 * consultant infer that a flagged citation has already been discounted.
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
  const rejectedExamples = result.citations_rejected_examples ?? [];

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

      {needsReview > 0 ? (
        <p
          className="text-status-warning-fg"
          data-testid="attack-citations-review"
        >
          Applied, but the name had to be resolved rather than matched — review
          before release
          {reviewTools.length > 0 ? `: ${joinCapped(reviewTools)}` : ""}. These
          still count toward the coverage score.
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
          . A technique whose only evidence was dropped now reads as uncovered.
        </p>
      ) : null}
    </div>
  );
}
