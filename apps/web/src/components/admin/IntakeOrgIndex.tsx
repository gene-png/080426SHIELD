"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import {
  Card,
  CardBody,
  EmptyState,
  StatusPill,
  type StatusTone,
} from "@shield/design-system";

import { listClients, type ClientSummary } from "@/lib/admin/client";
import {
  DEFAULT_ORG_FILTERS,
  filterOrganizations,
  type OrgFilters,
} from "@/lib/admin/filters";

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
  // IA appendix: filter the index by name, and by whether work is waiting.
  const [filters, setFilters] = React.useState<OrgFilters>(DEFAULT_ORG_FILTERS);

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

  const router = useRouter();

  // Alphabetical, always. The API returns creation order, which for 78 tenants
  // means "find your client by scrolling and hoping". A stable A-Z order is the
  // difference between scanning and searching.
  const byName = React.useMemo(
    () =>
      (clients ?? []).slice().sort((a, b) =>
        a.legal_name.localeCompare(b.legal_name, undefined, {
          sensitivity: "base",
        }),
      ),
    [clients],
  );

  // Legal names are NOT unique — three separate tenants share the name
  // "Northwind Grid Cooperative". Rendering them as identical rows is exactly
  // the confusion this page is meant to remove, so duplicates get disambiguated
  // by industry and intake date rather than silently collapsed (they really are
  // different tenants with different work).
  const duplicateNames = React.useMemo(() => {
    const seen = new Map<string, number>();
    for (const c of byName) {
      const key = c.legal_name.toLowerCase();
      seen.set(key, (seen.get(key) ?? 0) + 1);
    }
    return new Set(
      [...seen.entries()].filter(([, n]) => n > 1).map(([name]) => name),
    );
  }, [byName]);

  const visible = clients ? filterOrganizations(byName, filters) : [];

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

      {clients !== null && clients.length > 0 ? (
        /* The hint is referenced by aria-describedby rather than nested in the
           label: text inside a <label> becomes part of the control's ACCESSIBLE
           NAME, so a screen reader would announce the whole sentence every time
           the select took focus. */
        <div className="flex flex-col gap-1 text-sm">
          <label htmlFor="org-jump" className="font-medium text-ink-primary">
            Jump to an organization
          </label>
          <select
            id="org-jump"
            aria-describedby="org-jump-hint"
            // Deliberately uncontrolled-looking: this is a navigation control,
            // not a filter, so it resets to the placeholder after each jump
            // rather than pretending to hold a selection the page no longer has.
            value=""
            onChange={(e) => {
              if (e.target.value) router.push(`/admin/queue/${e.target.value}`);
            }}
            className="w-full rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            <option value="">
              {`Select from ${byName.length} organization${byName.length === 1 ? "" : "s"}…`}
            </option>
            {byName.map((c) => (
              <option key={c.id} value={c.id}>
                {c.legal_name}
                {c.open_request_count > 0
                  ? ` — ${c.open_request_count} awaiting review`
                  : ""}
              </option>
            ))}
          </select>
          <p id="org-jump-hint" className="text-xs text-ink-secondary">
            Every organization, A–Z. The list below stays filterable if you
            prefer to browse.
          </p>
        </div>
      ) : null}

      {clients !== null && clients.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex-1 text-sm">
            <span className="sr-only">Filter organizations by name</span>
            <input
              type="search"
              value={filters.query}
              onChange={(e) =>
                setFilters((f) => ({ ...f, query: e.target.value }))
              }
              placeholder="Filter by organization name…"
              className="w-full rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-secondary">
            <input
              type="checkbox"
              checked={filters.awaitingOnly}
              onChange={(e) =>
                setFilters((f) => ({ ...f, awaitingOnly: e.target.checked }))
              }
              className="h-4 w-4 rounded-sm border-border text-brand-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus"
            />
            Only awaiting review
          </label>
        </div>
      ) : null}

      {clients === null ? (
        <p className="text-sm text-ink-tertiary">Loading organizations…</p>
      ) : clients.length === 0 ? (
        <EmptyState
          title="No organizations yet"
          description="When a client registers and submits intake, they'll appear here."
        />
      ) : visible.length === 0 ? (
        /* Filtered to nothing. Say so explicitly — a bare "none" here reads as
           "no organizations exist", which is not what happened. */
        <EmptyState
          title="No organizations match these filters"
          description={`${clients.length} ${clients.length === 1 ? "organization is" : "organizations are"} hidden by the filters above. Clear them to see everything.`}
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {visible.map((c) => (
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
                        {duplicateNames.has(c.legal_name.toLowerCase()) ? (
                          /* Leading space is inside the span deliberately: CSS
                             margin does not separate words in the ACCESSIBLE
                             NAME, so without it a screen reader announces
                             "Cooperative(id 5b1e3d06)". */
                          <span className="font-normal text-xs text-ink-tertiary">
                            {" "}
                            (id {c.id.slice(0, 8)})
                          </span>
                        ) : null}
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
