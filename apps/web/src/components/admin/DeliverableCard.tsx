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

import Link from "next/link";

import {
  finalizeDeliverable,
  releaseDeliverable,
  TechDebtProxyError,
} from "@/lib/tech_debt/client";
import type { CapabilityListStatus, Deliverable } from "@/lib/tech_debt/types";

import type { JSX } from "react";

export interface DeliverableCardProps {
  serviceId: string;
  capabilityListStatus: CapabilityListStatus | null;
  deliverable: Deliverable | null;
  onChange: (next: Deliverable) => void;
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
  if (err instanceof TechDebtProxyError) {
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

export function DeliverableCard({
  serviceId,
  capabilityListStatus,
  deliverable,
  onChange,
}: DeliverableCardProps): JSX.Element {
  const [busy, setBusy] = React.useState<"finalize" | "release" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [confirmingRelease, setConfirmingRelease] = React.useState(false);

  const canFinalize = capabilityListStatus === "approved";
  const released = Boolean(deliverable?.released_at);

  async function onFinalize(): Promise<void> {
    setBusy("finalize");
    setError(null);
    try {
      const next = await finalizeDeliverable(serviceId);
      onChange(next);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  /**
   * Issue 4: release the finalized deliverable to the client.
   *
   * The API and the client wrapper for this both existed already —
   * `releaseDeliverable()` had ZERO callers, so nothing in the product could
   * ever satisfy the client dashboards' release gate. Wiring it here is what
   * makes a client able to see a dashboard at all.
   */
  async function onRelease(): Promise<void> {
    if (!deliverable) return;
    setBusy("release");
    setError(null);
    try {
      const next = await releaseDeliverable(deliverable.id);
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
          Render the PDF + XLSX from the approved capability list. Deliverables
          are admin-only — download and share them outside the app. Re-finalize
          on the same day appends <code>_v2</code> to the filename.
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

        {/* Issue 4: the admin's own view of the dashboard, available as soon as
            the deliverable is finalized — before release. Previously finalize
            produced a PDF and an XLSX and nothing else, so an analyst released
            to the client without ever seeing what the client would see. */}
        {deliverable ? (
          <Link
            href={`/dashboards/tech-debt/${serviceId}`}
            className="w-fit rounded-md border border-border bg-surface-card px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken"
          >
            View dashboard{released ? "" : " (preview)"} →
          </Link>
        ) : null}

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
              ? "Finalizing…"
              : deliverable
                ? "Re-finalize"
                : "Finalize"}
          </button>
          {!canFinalize && !deliverable ? (
            <span className="text-xs text-ink-tertiary">
              Approve the capability list to enable finalize.
            </span>
          ) : null}

          {/* Issue 4: release to the client. Behind an explicit confirm — it is
              the moment the client can first see this work. */}
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
