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

import {
  ClientScopedPage,
  type ClientScopedBodyProps,
} from "@/components/admin/ClientScopedPage";
import type { ClientOption } from "@/lib/admin/client-choice";
import {
  fetchAdminDeliverables,
  type AdminDeliverableRow,
  type DeliverableStatus,
} from "@/lib/admin/deliverables";

import type { JSX } from "react";

/**
 * IA appendix: "Deliverables — draft, approved, generated and released
 * products; version history and client-visible status."
 *
 * Deliverables were only ever visible one service workspace at a time, so an
 * admin answering "what have we produced, and what has the client actually
 * seen?" had to open every workspace in turn — the admin-side twin of the
 * scattered-results problem `/results` fixed for clients.
 *
 * Every row here is READ-ONLY. Finalize and release stay in the workspace that
 * owns the service: this surface answers "where is everything", and adding a
 * release button to a cross-service list is exactly how someone releases the
 * wrong version to the wrong tenant.
 */

const STATUS_TONE: Record<DeliverableStatus, StatusTone> = {
  released: "success",
  generated: "info",
  withheld: "warning",
  superseded: "neutral",
};

const STATUS_LABEL: Record<DeliverableStatus, string> = {
  released: "Released",
  generated: "Generated",
  // #556: released, and withheld from the client (another ATT&CK catalog).
  withheld: "Withheld from client",
  superseded: "Superseded",
};

// UTC, like the dashboards' released badge (`dashboards/shared.tsx`): the
// same release must read as the same day on every page, for every reader.
const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

/** Workspace route for a service kind — where the actions actually live. */
const WORKSPACE_PATH: Record<string, string> = {
  tech_debt: "tech-debt",
  nist_csf: "csf",
  attack_coverage: "attack-coverage",
  zero_trust_cisa: "zero-trust-cisa",
  zero_trust_dod: "zero-trust-dod",
};

function workspaceHref(row: AdminDeliverableRow): string | null {
  const seg = WORKSPACE_PATH[row.service_kind.toLowerCase()];
  return seg ? `/admin/services/${row.service_id}/${seg}` : null;
}

/** Group rows by service, preserving the API's ordering within each group. */
function groupByService(
  rows: AdminDeliverableRow[],
): { serviceId: string; title: string; rows: AdminDeliverableRow[] }[] {
  const out: {
    serviceId: string;
    title: string;
    rows: AdminDeliverableRow[];
  }[] = [];
  for (const row of rows) {
    const last = out[out.length - 1];
    if (last && last.serviceId === row.service_id) {
      last.rows.push(row);
      continue;
    }
    out.push({
      serviceId: row.service_id,
      title: row.service_title,
      rows: [row],
    });
  }
  return out;
}

/**
 * The page's own identity. Rendered by EVERY branch — loading, empty, error and
 * "no client picked" alike — because a state that drops the heading leaves the
 * reader with no way to tell a broken app from a page that simply has nothing
 * to show. It also stops s40's heading assertion from being a proxy for
 * "the page works" when it is not.
 */
function PageHeader({ chosen }: { chosen: ClientOption | null }): JSX.Element {
  // RR-2 (for #1121): the heading names the chosen client, and the subtitle
  // ("this organization") shows only when one is chosen. In every other state
  // there is no organization, and that state's own line says why.
  return (
    <header className="space-y-1">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
        Admin
      </p>
      <h1 className="text-3xl font-semibold text-ink-primary">
        {chosen ? `Deliverables for ${chosen.label}` : "Deliverables"}
      </h1>
      {chosen ? (
        <p className="max-w-prose text-sm text-ink-secondary">
          Every report produced for this organization, including the ones the
          client cannot see yet. Only{" "}
          <strong className="font-semibold text-ink-primary">Released</strong>{" "}
          rows are visible to the client.
        </p>
      ) : null}
    </header>
  );
}

/** §7 string 5, approved verbatim (#736 6130838759). */
const DELIVERABLES_NO_CLIENT =
  "Deliverables are listed per client. Choose a client above, then select Show this client.";

/**
 * RR-2 (for #1121): scoped by the page's own client picker
 * (`ClientScopedPage`), not by the shared active-client cookie. The frame
 * renders the header in every state, and the "pick a client" state that used
 * to live here (the upstream answers a missing X-Client-Id with a 400, so
 * asking without a client could only show "Failed to load deliverables (400).").
 */
export function DeliverablesTable(): JSX.Element {
  return (
    <ClientScopedPage
      header={(chosen) => <PageHeader chosen={chosen} />}
      noClient={
        <EmptyState
          title="Pick a client first"
          description={DELIVERABLES_NO_CLIENT}
        />
      }
      loadingText="Loading deliverables…"
    >
      {(props) => <DeliverablesBody {...props} />}
    </ClientScopedPage>
  );
}

/** Read-only, so there is no work in flight to lock the picker with. */
function DeliverablesBody({ client }: ClientScopedBodyProps): JSX.Element {
  const clientId = client.id;
  const [rows, setRows] = React.useState<AdminDeliverableRow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      try {
        const data = await fetchAdminDeliverables(clientId, controller.signal);
        if (!cancelled) setRows(data.items);
      } catch (err: unknown) {
        // An aborted request was superseded, not failed.
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load deliverables.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [clientId]);

  if (error) {
    // The page header stays: the frame renders it above this body. It used to
    // return the bare error card, so a failed fetch erased the page's own
    // identity: no "Deliverables" heading, nothing to orient on.
    return (
      <div className="flex flex-col gap-6">
        <Card>
          <CardBody>
            <p className="text-sm text-status-danger-fg" role="alert">
              {error}
            </p>
          </CardBody>
        </Card>
      </div>
    );
  }

  const groups = rows ? groupByService(rows) : [];
  const releasedCount = rows?.filter((r) => r.client_visible).length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {rows === null ? (
        <p className="text-sm text-ink-secondary">Loading deliverables…</p>
      ) : rows.length === 0 ? (
        <EmptyState
          title="No deliverables yet"
          description="Generate a report from a service workspace and it will appear here, released or not."
        />
      ) : (
        <>
          <p className="text-sm text-ink-secondary">
            {rows.length} {rows.length === 1 ? "version" : "versions"} across{" "}
            {groups.length} {groups.length === 1 ? "service" : "services"} ·{" "}
            {releasedCount} visible to the client
          </p>
          {groups.map((group) => (
            <Card key={group.serviceId}>
              <CardBody className="flex flex-col gap-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-sm font-semibold text-ink-primary">
                    {group.title}
                  </h2>
                  {workspaceHref(group.rows[0]) ? (
                    <Link
                      href={workspaceHref(group.rows[0]) as string}
                      className="text-sm font-semibold text-brand-600 hover:text-brand-500"
                    >
                      Open workspace →
                    </Link>
                  ) : null}
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[42rem] text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-ink-tertiary">
                      <tr>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Version
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Status
                        </th>
                        {/* "on" matters: a bare "Generated" column header
                            collides with the Generated status in the column
                            beside it, and the two mean different things. */}
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Generated on
                        </th>
                        <th scope="col" className="py-2 pr-4 font-medium">
                          Released on
                        </th>
                        <th scope="col" className="py-2 font-medium">
                          Files
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.rows.map((row) => (
                        <tr
                          key={row.id}
                          className="border-t border-border-subtle"
                        >
                          <th
                            scope="row"
                            className="py-2 pr-4 font-medium text-ink-primary"
                          >
                            v{row.version}
                          </th>
                          <td className="py-2 pr-4">
                            <StatusPill tone={STATUS_TONE[row.status]} withDot>
                              {STATUS_LABEL[row.status]}
                            </StatusPill>
                          </td>
                          <td className="py-2 pr-4 text-ink-secondary">
                            {formatDate(row.finalized_at)}
                          </td>
                          <td className="py-2 pr-4 text-ink-secondary">
                            {formatDate(row.released_at)}
                          </td>
                          <td className="py-2">
                            <span className="flex flex-wrap gap-3">
                              {(
                                [
                                  ["PDF", row.pdf_artifact_id],
                                  ["XLSX", row.xlsx_artifact_id],
                                  ["DOCX", row.docx_artifact_id],
                                ] as const
                              )
                                .filter(([, id]) => id)
                                .map(([label, id]) => (
                                  <a
                                    key={label}
                                    // RR-2 (for #1121), §3.2a: the picker's
                                    // client, never the cookie's.
                                    href={`/api/proxy/artifacts/${id}/download?client_id=${encodeURIComponent(clientId)}`}
                                    className="font-semibold text-brand-600 hover:text-brand-500"
                                  >
                                    {label}
                                  </a>
                                ))}
                              {!row.pdf_artifact_id &&
                              !row.xlsx_artifact_id &&
                              !row.docx_artifact_id ? (
                                <span className="text-ink-tertiary">—</span>
                              ) : null}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardBody>
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
