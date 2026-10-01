"use client";

import type { UseAiRun } from "@/lib/aiRuns/useAiRun";
import type { JSX } from "react";

/** Local wall-clock time of an api timestamp, e.g. "14:05". */
export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Where a Run-AI stands, for any service's workspace (#645).
 *
 * Three things a consultant could otherwise only guess at:
 *
 * - **A run is in progress**, so editing is locked, and until WHEN at the
 *   latest. There is no manual unlock; a hung run is ended by its deadline,
 *   so the deadline is the honest answer to "how long".
 * - **The page could not check.** A poll that fails to reach the api says
 *   so, and never says the run failed: only the api knows that.
 * - **The newest run failed**, with the api's own reason, and whether a
 *   provider probably charged for it -- three values, because "not known" is
 *   a real answer and reading it as "no" would flatter the run.
 *
 * A completed run's own disclosures (partial batches, dropped citations) are
 * the service's to render, from the run's stored result.
 */
export function AiRunStatus<R>({
  run,
}: {
  run: Pick<
    UseAiRun<R>,
    "phase" | "loadError" | "running" | "latest" | "checkFailed"
  >;
}): JSX.Element | null {
  if (run.phase === "error") {
    return (
      <p
        className="text-sm text-status-warning-fg"
        data-testid="ai-run-load-failed"
      >
        Could not check whether an AI run is in progress here
        {run.loadError ? ` (${run.loadError})` : ""}. If one is, the server will
        refuse edits until it finishes.
      </p>
    );
  }
  if (run.running) {
    return (
      <div className="flex flex-col gap-1 text-sm" aria-live="polite">
        <p className="text-ink-primary" data-testid="ai-run-running">
          <span className="font-semibold">AI run in progress</span>
          {run.running.serves === "offline" ? " (offline output)" : ""}. Editing
          this assessment is locked until it finishes, or until{" "}
          {clockTime(run.running.deadline_at)} at the latest.
        </p>
        {run.checkFailed ? (
          <p
            className="text-status-warning-fg"
            data-testid="ai-run-check-failed"
          >
            Could not check on the run just now, so it may still be running.
            Checking again.
          </p>
        ) : null}
      </div>
    );
  }
  const latest = run.latest;
  if (latest && latest.status === "failed") {
    return (
      <p
        className="text-sm text-status-danger-fg"
        role="alert"
        data-testid="ai-run-failed"
      >
        <span className="font-semibold">The last AI run failed.</span>{" "}
        {latest.error_message ?? latest.error_reason ?? ""}{" "}
        {latest.charged_likely === true
          ? "It made live AI calls, so the provider has probably charged for them."
          : latest.charged_likely === false
            ? "It made no live AI call."
            : "Whether it made a billable AI call is not known."}
      </p>
    );
  }
  return null;
}
