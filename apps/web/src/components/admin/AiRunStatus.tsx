"use client";

import type { AiRun } from "@/lib/aiRuns/types";
import type { UseAiRun } from "@/lib/aiRuns/useAiRun";
import type { JSX } from "react";

/** Local date and time of an api timestamp, e.g. "Oct 1, 2026, 14:05". */
export function whenText(iso: string): string {
  return new Date(iso).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * Where a Run-AI stands, for any service's workspace (#645).
 *
 * What a consultant could otherwise only guess at:
 *
 * - **A run is in progress**, so editing is locked, and until WHEN at the
 *   latest: `lock_until`, the run's deadline plus the margin before a status
 *   read ends it. There is no manual unlock.
 * - **The page could not check.** A poll that fails to reach the api says so
 *   and keeps looking; it never says the run failed: only the api knows that.
 * - **The api refused the read**, with its own message; or the run is past
 *   the latest it could hold the lock and still could not be read.
 * - **The newest run failed**, with the api's own reason, and whether a
 *   provider charged for it -- three values, because "not known" is a real
 *   answer and reading it as "no" would flatter the run.
 *
 * A completed run's own disclosures (partial batches, dropped citations) are
 * the service's to render, from the run's stored result.
 */
export function AiRunStatus<R>({
  run,
}: {
  run: Pick<
    UseAiRun<R>,
    | "phase"
    | "loadError"
    | "running"
    | "latest"
    | "checkFailed"
    | "pollRefused"
    | "pastLockUntil"
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
  if (run.pollRefused) {
    return (
      <p
        className="text-sm text-status-danger-fg"
        role="alert"
        data-testid="ai-run-poll-refused"
      >
        Could not follow the AI run: {run.pollRefused}
      </p>
    );
  }
  if (run.pastLockUntil) {
    return (
      <p
        className="text-sm text-status-warning-fg"
        role="alert"
        data-testid="ai-run-past-lock"
      >
        This AI run is past the latest it could run, and its outcome could not
        be read. Reload the page to see how it ended.
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
          {whenText(run.running.lock_until)} at the latest.
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
            : "It may have made a live AI call, which the provider may charge for: nothing on record says either way."}
      </p>
    );
  }
  return null;
}

/** Which run the disclosures below come from, with its date (#271). */
export function LastRunNote<R>({
  run,
}: {
  run: AiRun<R> | null;
}): JSX.Element | null {
  if (!run?.finished_at) return null;
  return (
    <p className="text-xs text-ink-tertiary" data-testid="ai-run-from">
      From the last AI run on this assessment that completed, on{" "}
      {whenText(run.finished_at)}.
    </p>
  );
}
