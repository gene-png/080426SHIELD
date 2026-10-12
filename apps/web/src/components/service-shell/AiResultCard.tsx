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
 * Every label is the CALLER's until the advisor approves fixed ones: the
 * figure labels ("Asked", "Applied", ...) and the next-step label ("What to
 * do next") arrive as props. Tone and outcome are caller-ASSERTED: the card
 * cannot check that a "success" tone matches the figures, so the page that
 * computes the run's accounting owns that truth. Tone sets colour only. A
 * tone for "status unknown" would be new design; it is proposed, not built.
 *
 * Refused, loudly: a blank outcome, a figure that is not a whole number from
 * zero, and reasons that do not add up to their figure (rule 7: exclusions
 * sit beside the figure, so they must account for all of it).
 */
export type AiResultTone = "success" | "warning" | "failure";

export type AiResultFigure = {
  label: string;
  value: number;
  /** A breakdown by reason, e.g. for "not applied". Must sum to `value`. */
  reasons?: readonly { reason: string; count: number }[];
};

const TONE_CLASS: Record<AiResultTone, string> = {
  success:
    "border-status-success-border bg-status-success-bg text-status-success-fg",
  warning:
    "border-status-warning-border bg-status-warning-bg text-status-warning-fg",
  failure:
    "border-status-danger-border bg-status-danger-bg text-status-danger-fg",
};

function isCount(n: number): boolean {
  return Number.isInteger(n) && n >= 0;
}

function checkFigure(figure: AiResultFigure): void {
  if (!isCount(figure.value)) {
    throw new Error(
      `AiResultCard: figure "${figure.label}" is ${figure.value}, not a whole number from zero.`,
    );
  }
  if (!figure.reasons) return;
  if (!figure.reasons.every((r) => isCount(r.count))) {
    throw new Error(
      `AiResultCard: a reason under "${figure.label}" has a count that is not a whole number from zero.`,
    );
  }
  const sum = figure.reasons.reduce((total, r) => total + r.count, 0);
  if (sum !== figure.value) {
    throw new Error(
      `AiResultCard: the reasons under "${figure.label}" add up to ${sum}, not ${figure.value}.`,
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
  /** Asked / applied / not applied (by reason) / unscored, in that order. */
  figures?: readonly AiResultFigure[];
  nextStep?: { label: string; content: ReactNode };
  children?: ReactNode;
}): JSX.Element {
  if (!outcome.trim()) {
    throw new Error("AiResultCard: a blank outcome; the card leads with it.");
  }
  figures?.forEach(checkFigure);
  return (
    <div
      data-testid="ai-result-card"
      className={
        "flex flex-col gap-2 rounded-md border p-4 " + TONE_CLASS[tone]
      }
    >
      <p className="text-base font-semibold">{outcome}</p>
      {figures && figures.length > 0 ? (
        <dl
          data-testid="ai-result-figures"
          className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm text-ink-primary"
        >
          {figures.map((figure) => (
            <div key={figure.label} className="contents">
              <dt className="font-semibold">{figure.label}</dt>
              <dd>
                {figure.value}
                {figure.reasons && figure.reasons.length > 0 ? (
                  <ul className="list-disc pl-5">
                    {figure.reasons.map((r) => (
                      <li key={r.reason}>
                        {r.reason} {r.count}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {children ? (
        <div className="text-sm text-ink-primary">{children}</div>
      ) : null}
      {nextStep ? (
        <div data-testid="ai-result-next" className="text-sm text-ink-primary">
          <p className="font-semibold">{nextStep.label}</p>
          <div>{nextStep.content}</div>
        </div>
      ) : null}
    </div>
  );
}
