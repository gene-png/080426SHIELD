import { hasContent, requireText } from "./guards";

import type { JSX, ReactNode } from "react";

/**
 * The AI result card: the AFTER stage of plan v2's rule 8 (#736,
 * issuecomment-6116093149), "a result card that leads with the outcome in one
 * sentence, then asked / applied / not applied (by reason) / unscored, then
 * 'What to do next'". Rule 8's BEFORE and DURING stages (what will be sent,
 * how long, "you can leave this page", progress) belong to the pilot's AI
 * draft section, not to this card.
 *
 * Order is fixed: outcome, then the figures, then any detail, then the next
 * step. The outcome is the card's first text: no heading or tone word goes in
 * front of it.
 *
 * The labels "Asked", "Applied", "Not applied", "Unscored" and "What to do
 * next" are the advisor's, approved verbatim (#736, issuecomment-6128447366).
 * Tone and outcome are caller-ASSERTED: the card cannot check that a "success"
 * tone matches the figures, so the page that computes the run's accounting
 * owns that truth. Tone sets colour only. A tone for "status unknown" would be
 * new design; it is proposed, not built.
 *
 * Refused, loudly. CALLER bugs: an unknown tone; a blank outcome; empty
 * next-step content. DATA-driven, from the run's accounting, which a mounting
 * page must expect until apps/web has an error boundary: a count that is not
 * a whole number from zero, a blank reason, and not-applied reasons that do
 * not add up to the not-applied count (rule 7: exclusions sit beside the
 * figure, so they must account for all of it). `children` is optional detail
 * and is exempt: an absent detail leaves nothing dangling.
 */
export type AiResultTone = "success" | "warning" | "failure";

export type AiResultFigures = {
  asked: number;
  applied: number;
  notApplied: number;
  /** Why rows were not applied. When given, must sum to `notApplied`. */
  notAppliedReasons?: readonly { reason: string; count: number }[];
  unscored: number;
};

const TONE_CLASS: Record<AiResultTone, string> = {
  success:
    "border-status-success-border bg-status-success-bg text-status-success-fg",
  warning:
    "border-status-warning-border bg-status-warning-bg text-status-warning-fg",
  failure:
    "border-status-danger-border bg-status-danger-bg text-status-danger-fg",
};

const NOT_APPLIED = "Not applied";

function isCount(n: number): boolean {
  return Number.isInteger(n) && n >= 0;
}

function checkCount(label: string, value: number): void {
  if (!isCount(value)) {
    throw new Error(
      `AiResultCard: "${label}" is ${value}, not a whole number from zero.`,
    );
  }
}

function checkFigures(figures: AiResultFigures): void {
  checkCount("Asked", figures.asked);
  checkCount("Applied", figures.applied);
  checkCount(NOT_APPLIED, figures.notApplied);
  checkCount("Unscored", figures.unscored);
  const reasons = figures.notAppliedReasons;
  if (!reasons) return;
  reasons.forEach((r) =>
    requireText("AiResultCard", `reason under "${NOT_APPLIED}"`, r.reason),
  );
  if (!reasons.every((r) => isCount(r.count))) {
    throw new Error(
      `AiResultCard: a reason under "${NOT_APPLIED}" has a count that is not a whole number from zero.`,
    );
  }
  const sum = reasons.reduce((total, r) => total + r.count, 0);
  if (sum !== figures.notApplied) {
    throw new Error(
      `AiResultCard: the reasons under "${NOT_APPLIED}" add up to ${sum}, not ${figures.notApplied}.`,
    );
  }
}

export function AiResultCard({
  outcome,
  tone,
  figures,
  nextStep,
  children,
}: {
  /** One sentence, the card's first text. */
  outcome: string;
  tone: AiResultTone;
  figures?: AiResultFigures;
  /** Shown under "What to do next". */
  nextStep?: ReactNode;
  children?: ReactNode;
}): JSX.Element {
  if (!Object.hasOwn(TONE_CLASS, tone)) {
    throw new Error(`AiResultCard: unknown tone "${tone}".`);
  }
  if (!outcome.trim()) {
    throw new Error("AiResultCard: a blank outcome; the card leads with it.");
  }
  if (figures) checkFigures(figures);
  if (nextStep !== undefined && !hasContent(nextStep)) {
    throw new Error("AiResultCard: empty next-step content.");
  }
  return (
    <div
      data-testid="ai-result-card"
      className={
        "flex flex-col gap-2 rounded-md border p-4 " + TONE_CLASS[tone]
      }
    >
      <p className="text-base font-semibold">{outcome}</p>
      {figures ? (
        <dl
          data-testid="ai-result-figures"
          className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm text-ink-primary"
        >
          <dt className="font-semibold">Asked</dt>
          <dd>{figures.asked}</dd>
          <dt className="font-semibold">Applied</dt>
          <dd>{figures.applied}</dd>
          <dt className="font-semibold">Not applied</dt>
          <dd>
            {figures.notApplied}
            {figures.notAppliedReasons &&
            figures.notAppliedReasons.length > 0 ? (
              <ul className="list-disc pl-5">
                {figures.notAppliedReasons.map((r) => (
                  <li key={r.reason}>
                    {r.reason} {r.count}
                  </li>
                ))}
              </ul>
            ) : null}
          </dd>
          <dt className="font-semibold">Unscored</dt>
          <dd>{figures.unscored}</dd>
        </dl>
      ) : null}
      {children ? (
        <div className="text-sm text-ink-primary">{children}</div>
      ) : null}
      {nextStep !== undefined ? (
        <div data-testid="ai-result-next" className="text-sm text-ink-primary">
          <p className="font-semibold">What to do next</p>
          <div>{nextStep}</div>
        </div>
      ) : null}
    </div>
  );
}
