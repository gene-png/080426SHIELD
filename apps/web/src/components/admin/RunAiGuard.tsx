"use client";
import Link from "next/link";
import * as React from "react";

import {
  acknowledgeOffline,
  hasAcknowledgedOffline,
  useAiStatus,
} from "@/lib/admin/aiStatus";

import type { JSX } from "react";

/**
 * Issue 2: intercept a Run-AI click while no API key is loaded.
 *
 * Wraps any Run-AI control. When AI is ready, or the admin already
 * acknowledged offline mode for THIS configuration, the child renders
 * untouched and the click goes straight through — no extra step in the happy
 * path. Otherwise the first click shows a choice: load a key, or knowingly
 * continue and get a canned offline response.
 *
 * The acknowledgement is scoped to the current configuration (see
 * `aiStatusKey`), so removing the key invalidates it: the next Run-AI in the
 * same session warns again rather than silently reusing an "I know" from
 * before the key was removed.
 */
export function RunAiGuard({
  onProceed,
  children,
}: {
  /** Runs when AI is ready, already acknowledged, or the admin chooses to continue offline. */
  onProceed: () => void;
  /** The Run-AI control. Receives the click handler to attach. */
  children: (props: { onClick: () => void }) => React.ReactNode;
}): JSX.Element {
  const { status } = useAiStatus();
  const [prompting, setPrompting] = React.useState(false);

  function handleClick(): void {
    // Unknown status must not block work — fail open to the existing behaviour.
    if (!status || status.ready || hasAcknowledgedOffline(status)) {
      onProceed();
      return;
    }
    setPrompting(true);
  }

  function continueOffline(): void {
    if (status) acknowledgeOffline(status);
    setPrompting(false);
    onProceed();
  }

  return (
    <>
      {children({ onClick: handleClick })}
      {prompting && status ? (
        <div
          role="alertdialog"
          aria-label="No API key loaded"
          className="mt-3 rounded-md border border-status-warning-border bg-status-warning-bg px-4 py-3 text-sm"
        >
          <p className="font-semibold text-status-warning-fg">
            No API key is loaded — this will generate an offline response.
          </p>
          <p className="mt-1 text-ink-secondary">
            Offline (fixture) output is deterministic demo content, not analysis
            of this client&apos;s data. Load a key to run real AI.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              href="/admin/management#ai-provider-key"
              className="rounded-md bg-brand-500 px-3 py-1.5 text-xs font-semibold text-ink-on-accent hover:bg-brand-600"
            >
              Load a key
            </Link>
            <button
              type="button"
              onClick={continueOffline}
              className="rounded-md border border-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-ink-primary hover:bg-surface-sunken"
            >
              Continue offline
            </button>
            <button
              type="button"
              onClick={() => setPrompting(false)}
              className="rounded-md px-3 py-1.5 text-xs font-semibold text-ink-secondary hover:text-ink-primary"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
