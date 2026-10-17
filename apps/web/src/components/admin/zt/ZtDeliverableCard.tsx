"use client";
import Link from "next/link";
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
  finalizeZtDeliverable,
  releaseZtDeliverable,
  ZtProxyError,
} from "@/lib/zt/client";
import type { ZtAssessmentStatus, ZtDeliverable } from "@/lib/zt/types";

import type { JSX } from "react";
import { formatInstantUtc } from "@/lib/dates";

import { ZT_SECTION_COPY } from "./ztSections";

/**
 * #1379: which section's controls to show. "generate" is the status, the
 * downloads and Send for evaluation; "preview" is the client dashboard link;
 * "release" is the status and Release with its confirm. Absent, the whole
 * card, as before. The handlers are the same in every part.
 */
export type ZtDeliverablePart = "generate" | "preview" | "release";

export interface ZtDeliverableCardProps {
  serviceId: string;
  assessmentStatus: ZtAssessmentStatus | null;
  deliverable: ZtDeliverable | null;
  onChange: (next: ZtDeliverable) => void;
  part?: ZtDeliverablePart;
}

// UTC, naming the zone -- the same instant the admin deliverables table shows.
const fmtTime = formatInstantUtc;

function describeError(err: unknown): string {
  if (err instanceof ZtProxyError) {
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

export function ZtDeliverableCard({
  serviceId,
  assessmentStatus,
  deliverable,
  onChange,
  part,
}: ZtDeliverableCardProps): JSX.Element {
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
      const next = await finalizeZtDeliverable(serviceId);
      onChange(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  /**
   * Issue 4: release the finalized deliverable to the client. `releaseZtDeliverable`
   * already existed with ZERO callers, so nothing in the product could satisfy
   * the client dashboard's release gate until this was wired up.
   */
  async function onRelease(): Promise<void> {
    if (!deliverable) return;
    setBusy("release");
    setError(null);
    try {
      const next = await releaseZtDeliverable(deliverable.id);
      setConfirmingRelease(false);
      onChange(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  const showGenerate = part === undefined || part === "generate";
  const showPreview = part === undefined || part === "preview";
  const showRelease = part === undefined || part === "release";
  const copy = ZT_SECTION_COPY.deliverable;

  if (part === "preview" && !deliverable) {
    return <p className="text-sm text-ink-secondary">{copy.previewNone}</p>;
  }

  return (
    <Card>
      <CardHeader>
        {part === "release" ? (
          <>
            <CardTitle>{copy.releaseTitle}</CardTitle>
            <CardDescription>{copy.releaseDescription}</CardDescription>
          </>
        ) : (
          <>
            <CardTitle>Evaluation &amp; report</CardTitle>
            <CardDescription>
              Once you&apos;ve reviewed and approved the inputs, send for
              evaluation to run the gap analysis and produce the PDF + XLSX
              report. Reports are admin-only — download and share them outside
              the app. Re-running on the same day appends <code>_v2</code> to
              the filename.
            </CardDescription>
          </>
        )}
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

        {showGenerate && deliverable ? (
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

        {/* Issue 4: the admin's own view of the dashboard, live as soon as
            the deliverable is finalized — before release. */}
        {showPreview && deliverable ? (
          <Link
            href={`/dashboards/zt/${serviceId}`}
            className="w-fit rounded-md border border-border bg-surface-card px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken"
          >
            View dashboard{released ? "" : " (preview)"} →
          </Link>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          {showGenerate ? (
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
          ) : null}
          {showGenerate && !canFinalize && !deliverable ? (
            <span className="text-xs text-ink-tertiary">
              Approve the client inputs to enable evaluation.
            </span>
          ) : null}

          {/* Issue 4: release to the client — the moment they can first see
              this work, so it sits behind an explicit confirm. */}
          {showRelease && part === "release" && !deliverable ? (
            <span className="text-sm text-ink-secondary">
              {copy.releaseNone}
            </span>
          ) : null}
          {showRelease && deliverable && !released ? (
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
