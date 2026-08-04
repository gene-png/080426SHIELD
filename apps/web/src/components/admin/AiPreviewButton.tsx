"use client";
import * as React from "react";

import {
  AiPreviewError,
  fetchAiPreview,
  totalRemoved,
  type AiPreview,
} from "@/lib/ai/preview";

import type { JSX } from "react";

export interface AiPreviewButtonProps {
  serviceId: string;
  /** Disable while a sibling action (e.g. Run AI) is busy. */
  disabled?: boolean;
}

function describeError(err: unknown): string {
  if (err instanceof AiPreviewError) {
    const payload = err.payload as
      { error?: { reason?: string; message?: string } } | undefined;
    const detail = payload?.error;
    if (detail?.message) {
      return detail.message;
    }
    return `Preview failed (HTTP ${err.status}).`;
  }
  return "Preview failed. Please try again.";
}

/**
 * An OFFERED redaction-preview gate for a Run-AI surface (Sprint 5 T6). Shows
 * exactly what would be sent to the model AFTER redaction, plus how many spans
 * were stripped — WITHOUT egressing or recording a call. Non-blocking: Run AI
 * still works directly; this is a look-before-you-send affordance.
 */
export function AiPreviewButton({
  serviceId,
  disabled,
}: AiPreviewButtonProps): JSX.Element {
  const [busy, setBusy] = React.useState(false);
  const [preview, setPreview] = React.useState<AiPreview | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function onPreview(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      setPreview(await fetchAiPreview(serviceId));
    } catch (err) {
      setPreview(null);
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const counts = preview?.removed_counts ?? {};
  const total = totalRemoved(counts);

  return (
    <div className="flex flex-col gap-2" data-testid="ai-preview">
      <button
        type="button"
        onClick={() => void onPreview()}
        disabled={busy || disabled}
        data-testid="ai-preview-button"
        className="rounded-md border border-border-default px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? "Building preview…" : "Preview what will be sent"}
      </button>

      {error ? (
        <p className="text-sm text-status-danger-fg" role="alert">
          {error}
        </p>
      ) : null}

      {preview ? (
        <div
          className="flex flex-col gap-2 rounded-md border border-border-default bg-surface-muted p-3"
          data-testid="ai-preview-result"
        >
          <p className="text-sm text-ink-secondary" aria-live="polite">
            Nothing has been sent. This is the redacted payload for{" "}
            <span className="font-semibold text-ink-primary">
              {preview.purpose}
            </span>{" "}
            ({preview.redaction_mode} mode).{" "}
            <span
              className="font-semibold text-ink-primary"
              data-testid="ai-preview-removed-total"
            >
              {total}
            </span>{" "}
            span{total === 1 ? "" : "s"} redacted
            {total > 0
              ? ` (${Object.entries(counts)
                  .map(([k, n]) => `${k}: ${n}`)
                  .join(", ")})`
              : ""}
            .
          </p>
          <pre
            className="max-h-64 overflow-auto rounded bg-surface-default p-2 text-xs text-ink-secondary"
            data-testid="ai-preview-payload"
          >
            {JSON.stringify(preview.payload, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
