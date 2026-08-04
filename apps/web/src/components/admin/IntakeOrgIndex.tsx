"use client";
import Link from "next/link";
import * as React from "react";

import {
  Card,
  CardBody,
  EmptyState,
  StatusPill,
  type StatusTone,
} from "@shield/design-system";

import { listClients, type ClientSummary } from "@/lib/admin/client";

import type { JSX } from "react";

/**
 * Issue 7: the intake queue used to open straight onto ONE organization.
 *
 * `GET /admin/intake-queue` without a `client_id` returns every tenant's
 * service requests but sets the `client` field to whichever tenant was created
 * most recently — its own docstring calls that "advisory". The UI rendered that
 * advisory tenant as the page's Organization header, so an admin saw one
 * client's profile stapled above every client's work.
 *
 * The queue is now an index: pick an organization, then open it. Each row
 * carries the counts the API already computes, so an admin can see where the
 * work is without opening every org in turn.
 */

function tone(open: number): StatusTone {
  if (open > 0) return "warning";
  return "neutral";
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

export function IntakeOrgIndex(): JSX.Element {
  const [clients, setClients] = React.useState<ClientSummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    listClients()
      .then((rows) => {
        if (!cancelled) setClients(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load organizations.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
          Admin
        </p>
        <h1 className="text-3xl font-semibold text-ink-primary">
          Intake queue
        </h1>
        <p className="max-w-prose text-sm text-ink-secondary">
          Every organization that has registered. Open one to see its intake
          submission and the work waiting on you.
        </p>
      </header>

      {clients === null ? (
        <p className="text-sm text-ink-tertiary">Loading organizations…</p>
      ) : clients.length === 0 ? (
        <EmptyState
          title="No organizations yet"
          description="When a client registers and submits intake, they'll appear here."
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {clients.map((c) => (
            <li key={c.id}>
              <Link
                href={`/admin/queue/${c.id}`}
                className="block rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
              >
                <Card className="transition-colors hover:border-brand-500">
                  <CardBody className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink-primary">
                        {c.legal_name}
                      </p>
                      <p className="text-xs text-ink-secondary">
                        {c.industry ?? "Industry not set"} ·{" "}
                        {c.intake_completed_at
                          ? `Intake submitted ${formatDate(c.intake_completed_at)}`
                          : "Intake not submitted"}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      <StatusPill tone={tone(c.open_request_count)} withDot>
                        {c.open_request_count} awaiting review
                      </StatusPill>
                      <StatusPill tone="info">
                        {c.total_request_count} total
                      </StatusPill>
                    </div>
                  </CardBody>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
