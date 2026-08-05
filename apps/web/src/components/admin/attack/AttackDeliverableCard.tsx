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
  AttackProxyError,
  finalizeAttackDeliverable,
  releaseAttackDeliverable,
} from "@/lib/attack/client";
import type {
  AttackAssessmentStatus,
  AttackDeliverable,
} from "@/lib/attack/types";

import type { JSX } from "react";

export interface AttackDeliverableCardProps {
  serviceId: string;
  assessmentStatus: AttackAssessmentStatus | null;
  deliverable: AttackDeliverable | null;
  onChange: (next: AttackDeliverable) => void;
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
  if (err instanceof AttackProxyError) {
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

export function AttackDeliverableCard({
  serviceId,
  assessmentStatus,
  deliverable,
  onChange,
}: AttackDeliverableCardProps): JSX.Element {
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
      const next = await finalizeAttackDeliverable(serviceId);
      onChange(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  /**
   * Issue 4: release the finalized deliverable to the client. `releaseAttackDeliverable`
   * already existed with ZERO callers, so nothing in the product could satisfy
   * the client dashboard's release gate until this was wired up.
   */
  async function onRelease(): Promise<void> {
    if (!deliverable) return;
    setBusy("release");
    setError(null);
    try {
      const next = await releaseAttackDeliverable(deliverable.id);
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
        <CardTitle>Deliverable</CardTitle>
        <CardDescription>
          Render the PDF + XLSX from the approved coverage assessment. The PDF
          includes the per-tactic coverage table + top-50 gap list; the XLSX
          carries the full ~600-row coverage matrix.
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

        {/* Issue 4: the admin's own view of the dashboard, live as soon as
            the deliverable is finalized — before release. */}
        {deliverable ? (
          <Link
            href={`/dashboards/attack/${serviceId}`}
            className="w-fit rounded-md border border-border bg-surface-card px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken"
          >
            View dashboard{released ? "" : " (preview)"} →
          </Link>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void onFinalize()}
            disabled={!canFinalize || busy !== null}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "finalize"
              ? "Finalizing…"
              : deliverable
                ? "Re-finalize"
                : "Finalize"}
          </button>
          {!canFinalize && !deliverable ? (
            <span className="text-xs text-ink-tertiary">
              Approve the assessment to enable finalize.
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
