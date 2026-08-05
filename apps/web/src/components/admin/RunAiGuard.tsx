"use client";
import Link from "next/link";
import * as React from "react";

import {
  acknowledgeOffline,
  hasAcknowledgedOffline,
  useAiStatus,
} from "@/lib/admin/aiStatus";

import type { AiStatus } from "@/lib/admin/client";
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
 *
 * A click that lands BEFORE the status request resolves is held, not passed
 * through. The first cut failed open on `status === null`, which conflates
 * "still loading" with "endpoint down" — so under load the guard silently ran
 * and wrote 1646 fields of canned output (caught by the full-suite s34 run,
 * pinned by RunAiGuard.test.tsx). A genuine status outage still fails open:
 * an outage must not stop an admin working, but not-asked-yet is not an
 * outage.
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
  const { status, phase, settled } = useAiStatus();
  /** The status the open warning describes; non-null exactly while prompting. */
  const [promptFor, setPromptFor] = React.useState<AiStatus | null>(null);
  const [awaitingStatus, setAwaitingStatus] = React.useState(false);

  /** Decide what a click means, given a SETTLED status. */
  function decide(s: AiStatus | null): void {
    // A status OUTAGE fails open — it must not block work.
    if (!s || s.ready || hasAcknowledgedOffline(s)) {
      onProceed();
      return;
    }
    setPromptFor(s);
  }

  async function handleClick(): Promise<void> {
    if (phase !== "loading") {
      decide(status);
      return;
    }
    // Hold the click until we know. Proceeding here would be a silent
    // success — the one thing this component exists to prevent.
    setAwaitingStatus(true);
    const resolved = await settled();
    setAwaitingStatus(false);
    decide(resolved);
  }

  function continueOffline(): void {
    if (promptFor) acknowledgeOffline(promptFor);
    setPromptFor(null);
    onProceed();
  }

  return (
    <>
      {children({ onClick: handleClick })}
      {awaitingStatus ? (
        // Deliberately not role="status": /admin/health already owns that
        // landmark and a second one breaks its locator. aria-live announces it
        // without adding a competing status role.
        <p aria-live="polite" className="mt-2 text-xs text-ink-tertiary">
          Checking whether an API key is loaded…
        </p>
      ) : null}
      {promptFor ? (
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
              onClick={() => setPromptFor(null)}
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
