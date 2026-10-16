"use client";
import type { JSX } from "react";

import type {
  AttackAssessment,
  AttackCatalog,
  AttackCoverageRow,
} from "@/lib/attack/types";

/** The status words the panel prints. Admin copy, posted on #554 (A3). */
const STATUS_TEXT: Record<string, string> = {
  covered: "Covered",
  partial: "Partial",
  gap: "Gap",
  not_applicable: "N/A",
  outside_control_surface: "Outside control surface",
  unable_to_determine: "Not verified",
};

/** The client words for each value, COPIED from `IN_PLACE_TEXT` in
 *  `apps/api/app/attack/computed.py`; change both. Display only. */
const IN_PLACE_TEXT: Record<string, string> = {
  in_place: "in place",
  not_in_place: "not in place",
  awaiting_review: "awaiting review",
  cannot_be_prevented: "cannot be prevented",
};

function statusText(value: string | null | undefined): string {
  return value ? (STATUS_TEXT[value] ?? value) : "Unscored";
}

/** A row whose computed status differs from the stored suggestion and whose
 *  review accepted THAT computed status. */
function isReviewed(row: AttackCoverageRow): boolean {
  return (
    row.computed_status != null &&
    row.computed_status !== row.status &&
    row.reviewed_status === row.computed_status &&
    row.in_review_queue !== true
  );
}

interface TacticGroup {
  tactic: string;
  rows: AttackCoverageRow[];
}

/** The queue by tactic, in the catalog's tactic order, or null when the
 *  catalog cannot place every queued technique: a row with no group would be
 *  a row the panel does not show. A technique under several tactics is in
 *  each of their groups. */
function groupByTactic(
  queue: AttackCoverageRow[],
  catalog: AttackCatalog | null | undefined,
): TacticGroup[] | null {
  if (!catalog || queue.length === 0) return null;
  const tacticsOf = new Map(catalog.techniques.map((t) => [t.id, t.tactics]));
  if (queue.some((row) => !(tacticsOf.get(row.technique_code) ?? []).length)) {
    return null;
  }
  return catalog.tactics
    .map((tactic) => ({
      tactic: tactic.name,
      rows: queue.filter((row) =>
        (tacticsOf.get(row.technique_code) ?? []).includes(tactic.shortname),
      ),
    }))
    .filter((group) => group.rows.length > 0);
}

function reviewOf(rows: AttackCoverageRow[]) {
  return rows.map((row) => ({
    code: row.technique_code,
    computed_status: row.computed_status ?? "",
  }));
}

function count(n: number): string {
  return n.toLocaleString("en-US");
}

/** The queue's table: the code (with its catalog name when known), the AI's
 *  status, the computed one, and the three capability words. */
function ReviewTable({
  rows,
  nameOf,
}: {
  rows: AttackCoverageRow[];
  nameOf: Map<string, string>;
}): JSX.Element {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            <th scope="col">Technique</th>
            <th scope="col">AI suggested</th>
            <th scope="col">Computed</th>
            <th scope="col">Detect</th>
            <th scope="col">Prevent</th>
            <th scope="col">Respond</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.technique_code}>
              <td>
                <span className="font-mono">{row.technique_code}</span>
                {nameOf.has(row.technique_code)
                  ? ` ${nameOf.get(row.technique_code)}`
                  : null}
              </td>
              <td>{statusText(row.status)}</td>
              <td>{statusText(row.computed_status)}</td>
              <td>{IN_PLACE_TEXT[row.capabilities?.detect ?? ""] ?? ""}</td>
              <td>{IN_PLACE_TEXT[row.capabilities?.prevent ?? ""] ?? ""}</td>
              <td>{IN_PLACE_TEXT[row.capabilities?.respond ?? ""] ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface AttackComputedReviewPanelProps {
  assessment: AttackAssessment;
  /** #1052 / #1051: groups the queue by tactic and names each technique.
   *  Absent (still loading), or missing any queued technique, the queue is
   *  shown ungrouped, every row, as before. */
  catalog?: AttackCatalog | null;
  busy: boolean;
  /** Records the review of what this panel shows: each code with the computed
   *  status on screen, so the API can refuse one that moved since. */
  onReview: (
    reviews: { code: string; computed_status: string }[],
  ) => Promise<void> | void;
}

/**
 * #554 R3, the advisor's Q1 (2026-10-02, 22:20Z): on an assessment whose
 * statuses are computed from Detect / Prevent / Respond, each technique whose
 * computed status differs from the AI's suggestion is reviewed before release.
 * The release refusal names this panel ("the Computed status review panel"),
 * so it is rendered wherever that refusal can be met: a draft or an approved
 * assessment. Copy A1-A6 of the build plan on #554.
 */
export function AttackComputedReviewPanel({
  assessment,
  catalog,
  busy,
  onReview,
}: AttackComputedReviewPanelProps): JSX.Element | null {
  if (assessment.statuses_computed !== true) return null;
  if (assessment.status !== "draft" && assessment.status !== "approved") {
    return null;
  }
  const queue = assessment.coverage
    .filter((row) => row.in_review_queue === true)
    .sort((a, b) => a.technique_code.localeCompare(b.technique_code));
  const reviewed = assessment.coverage.filter(isReviewed).length;
  const shown = reviewOf(queue);
  const groups = groupByTactic(queue, catalog);
  const nameOf = new Map(
    groups ? (catalog?.techniques ?? []).map((t) => [t.id, t.name]) : [],
  );
  const multiTactic =
    groups !== null &&
    groups.reduce((n, g) => n + g.rows.length, 0) > queue.length;

  return (
    <section
      aria-labelledby="attack-computed-review-heading"
      data-testid="attack-computed-review"
      className="flex flex-col gap-3 rounded-md border border-line-subtle p-3"
    >
      <h3
        id="attack-computed-review-heading"
        className="text-sm font-semibold text-ink-primary"
      >
        Computed status review
      </h3>
      {queue.length === 0 && reviewed === 0 ? (
        <p className="text-sm text-ink-secondary">
          No technique&apos;s computed status differs from the AI&apos;s
          suggestion.
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-secondary">
            On this assessment, each technique&apos;s status is computed from
            its Detect, Prevent and Respond tools. These techniques&apos;
            computed status differs from the AI&apos;s suggestion. The
            deliverable cannot be released until each has been reviewed.
          </p>
          <p
            className="text-sm text-ink-primary"
            data-testid="attack-computed-review-status"
          >
            {`${reviewed} reviewed, ${queue.length} awaiting review.`}
          </p>
        </>
      )}
      {queue.length > 0 ? (
        <>
          {groups === null ? (
            <ReviewTable rows={queue} nameOf={nameOf} />
          ) : (
            <>
              {multiTactic ? (
                <p
                  className="text-sm text-ink-secondary"
                  data-testid="attack-computed-review-multi-tactic"
                >
                  PLACEHOLDER M-4c: a technique listed under more than one
                  tactic is marked reviewed everywhere it appears
                </p>
              ) : null}
              {groups.map((group) => (
                <div
                  key={group.tactic}
                  className="flex flex-col gap-2"
                  data-testid="attack-computed-review-group"
                >
                  <h4 className="text-sm font-semibold text-ink-primary">
                    {`PLACEHOLDER M-4a: ${group.tactic} (${count(group.rows.length)})`}
                  </h4>
                  <ReviewTable rows={group.rows} nameOf={nameOf} />
                  <div>
                    <button
                      type="button"
                      onClick={() => void onReview(reviewOf(group.rows))}
                      disabled={busy}
                      className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-60"
                    >
                      {`PLACEHOLDER M-4b: ${count(group.rows.length)} in ${group.tactic}`}
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}
          <div>
            <button
              type="button"
              onClick={() => void onReview(shown)}
              disabled={busy}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {queue.length === 1
                ? "Mark 1 as reviewed"
                : `Mark all ${queue.length} as reviewed`}
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
