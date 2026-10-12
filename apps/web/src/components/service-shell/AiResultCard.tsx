import type { JSX, ReactNode } from "react";

/**
 * The AI result card of Gene's UI page plan: "One AI-run pattern before,
 * during and after, with the result card leading with the outcome" (#736,
 * issuecomment-6115899349 rule 7).
 *
 * The outcome is the caller's sentence and is the card's first text: no
 * heading or tone word is added in front of it, because none is approved.
 * Tone sets colour only, so it never says anything the caller did not write.
 */
export type AiResultTone = "success" | "warning" | "failure";

const TONE_CLASS: Record<AiResultTone, string> = {
  success:
    "border-status-success-border bg-status-success-bg text-status-success-fg",
  warning:
    "border-status-warning-border bg-status-warning-bg text-status-warning-fg",
  failure:
    "border-status-danger-border bg-status-danger-bg text-status-danger-fg",
};

export function AiResultCard({
  outcome,
  tone,
  children,
}: {
  outcome: string;
  tone: AiResultTone;
  children?: ReactNode;
}): JSX.Element {
  return (
    <div
      data-testid="ai-result-card"
      className={
        "flex flex-col gap-2 rounded-md border p-4 " + TONE_CLASS[tone]
      }
    >
      <p className="text-base font-semibold">{outcome}</p>
      {children ? (
        <div className="text-sm text-ink-primary">{children}</div>
      ) : null}
    </div>
  );
}
