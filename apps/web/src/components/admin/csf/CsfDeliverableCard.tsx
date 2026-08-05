"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  StatusPill,
} from "@shield/design-system";

import {
  CsfProxyError,
  finalizeCsfDeliverable,
  releaseCsfDeliverable,
} from "@/lib/csf/client";
import type { CsfAssessmentStatus, CsfDeliverable } from "@/lib/csf/types";

import type { JSX } from "react";

export interface CsfDeliverableCardProps {
  serviceId: string;
  assessmentStatus: CsfAssessmentStatus | null;
  deliverable: CsfDeliverable | null;
  onChange: (next: CsfDeliverable) => void;
}

function fmtTime(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function describeError(err: unknown): string {
  if (err instanceof CsfProxyError) {
    const payload = err.payload as
      { error?: { message?: string }; detail?: string } | undefined;
    return (
      payload?.error?.message ??
      payload?.detail ??
      `Request failed (${err.status}).`
    );
  }
  return err instanceof Error ? err.message : "Request failed.";
}

export function CsfDeliverableCard({
  serviceId,
  assessmentStatus,
  deliverable,
  onChange,
}: CsfDeliverableCardProps): JSX.Element {
  const [busy, setBusy] = React.useState<"finalize" | "release" | null>(null);
  const [confirmingRelease, setConfirmingRelease] = React.useState(false);
  const released = Boolean(deliverable?.released_at);
  const [error, setError] = React.useState<string | null>(null);

  const canFinalize =
    assessmentStatus === "approved" || assessmentStatus === "released";

  async function onFinalize(): Promise<void> {
    setBusy("finalize");
    setError(null);
    try {
      const next = await finalizeCsfDeliverable(serviceId);
      onChange(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  /**
   * Issue 4: release the finalized deliverable to the client. `releaseCsfDeliverable`
   * already existed with ZERO callers, so nothing in the product could satisfy
   * the client dashboard's release gate until this was wired up.
   */
  async function onRelease(): Promise<void> {
    if (!deliverable) return;
    setBusy("release");
    setError(null);
    try {
      const next = await releaseCsfDeliverable(deliverable.id);
      setConfirmingRelease(false);
      onChange(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Evaluation &amp; report</CardTitle>
        <CardDescription>
          Once you&apos;ve reviewed and approved the inputs, send for evaluation
          to run the gap analysis and produce the PDF + XLSX report. Reports are
          admin-only — download and share them outside the app. Re-running on
          the same day appends <code>_v2</code> to the filename.
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {deliverable ? (
            <>
              <StatusPill tone={released ? "success" : "info"} withDot>
                {released
                  ? `Released v${deliverable.version}`
                  : `Finalized v${deliverable.version}`}
              </StatusPill>
              <span className="text-xs text-ink-tertiary">
                {released
                  ? `Released ${fmtTime(deliverable.released_at)}`
                  : `Finalized ${fmtTime(deliverable.finalized_at)}`}
              </span>
            </>
          ) : (
            <StatusPill tone="neutral" withDot>
              Not finalized yet
            </StatusPill>
          )}
        </div>

        {deliverable ? (
          <ul className="space-y-1 text-sm">
            {deliverable.pdf_artifact_id ? (
              <li>
                <a
                  href={`/api/proxy/artifacts/${deliverable.pdf_artifact_id}/download`}
                  className="text-brand-500 underline hover:text-brand-600"
                >
                  {deliverable.pdf_filename ?? "Download PDF"}
                </a>
              </li>
            ) : null}
            {deliverable.xlsx_artifact_id ? (
              <li>
                <a
                  href={`/api/proxy/artifacts/${deliverable.xlsx_artifact_id}/download`}
                  className="text-brand-500 underline hover:text-brand-600"
                >
                  {deliverable.xlsx_filename ?? "Download XLSX"}
                </a>
              </li>
            ) : null}
          </ul>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void onFinalize()}
            disabled={!canFinalize || busy !== null}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "finalize"
              ? "Sending…"
              : deliverable
                ? "Re-run evaluation"
                : "Send for evaluation"}
          </button>
          {!canFinalize && !deliverable ? (
            <span className="text-xs text-ink-tertiary">
              Approve the client inputs to enable evaluation.
            </span>
          ) : null}

          {/* Issue 4: release to the client — the moment they can first see
              this work, so it sits behind an explicit confirm. */}
          {deliverable && !released ? (
            confirmingRelease ? (
              <span className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-ink-secondary">
                  Release v{deliverable.version} to the client?
                </span>
                <button
                  type="button"
                  onClick={() => void onRelease()}
                  disabled={busy !== null}
                  className="rounded-md bg-brand-500 px-3 py-1.5 text-xs font-semibold text-ink-on-accent disabled:opacity-60"
                >
                  {busy === "release" ? "Releasing…" : "Yes, release"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingRelease(false)}
                  disabled={busy !== null}
                  className="rounded-md border border-border bg-surface-card px-3 py-1.5 text-xs font-semibold text-ink-primary hover:bg-surface-sunken"
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmingRelease(true)}
                disabled={busy !== null}
                className="rounded-md border border-brand-500 px-4 py-2 text-sm font-semibold text-brand-600 hover:bg-brand-50 disabled:opacity-60"
              >
                Release to client
              </button>
            )
          ) : null}
        </div>

        {error ? (
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
