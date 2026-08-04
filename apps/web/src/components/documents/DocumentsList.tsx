import {
  DataTable,
  EmptyState,
  StatusPill,
  type DataTableColumn,
} from "@shield/design-system";

import { SERVICE_LABELS, type ServiceType } from "@/lib/intake/types";

import type { JSX } from "react";

/**
 * "WHAT YOU'VE RECEIVED" (Master Spec §6.7): the released deliverables a client
 * can read + download. Purely presentational and server-rendered — the release
 * rule (§12) is enforced upstream, so every row here is already released. Empty
 * renders the no-dead-ends guidance (§12), never a bare blank.
 *
 * Types mirror the backend `ClientDeliverableResponse`
 * (apps/api/app/schemas/clients.py): only RELEASED deliverables reach them.
 */

/** One released deliverable as the client sees it on /documents. */
export interface ClientDeliverable {
  id: string;
  service_id: string;
  service_kind: string;
  service_title: string;
  title: string;
  summary: string | null;
  version: number;
  released_at: string | null;
  superseded: boolean;
  pdf_artifact_id: string | null;
  xlsx_artifact_id: string | null;
  docx_artifact_id: string | null;
  pdf_filename: string | null;
  xlsx_filename: string | null;
  docx_filename: string | null;
}

/** Response envelope for GET /clients/{cid}/deliverables. */
export interface ClientDeliverableListResponse {
  items: ClientDeliverable[];
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function formatReleased(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

function serviceLabel(d: ClientDeliverable): string {
  return SERVICE_LABELS[d.service_kind as ServiceType] ?? d.service_title;
}

interface DownloadLink {
  artifactId: string;
  filename: string | null;
  label: string;
}

/** The client dashboard route for a service kind, or null if none exists yet. */
function dashboardPathFor(d: ClientDeliverable): string | null {
  switch (d.service_kind) {
    case "attack_coverage":
      return `/dashboards/attack/${d.service_id}`;
    case "zero_trust_cisa":
    case "zero_trust_dod":
      return `/dashboards/zt/${d.service_id}`;
    case "tech_debt":
      return `/dashboards/tech-debt/${d.service_id}`;
    default:
      return null;
  }
}

function downloadsFor(d: ClientDeliverable): DownloadLink[] {
  const links: DownloadLink[] = [];
  if (d.pdf_artifact_id)
    links.push({
      artifactId: d.pdf_artifact_id,
      filename: d.pdf_filename,
      label: "PDF",
    });
  if (d.xlsx_artifact_id)
    links.push({
      artifactId: d.xlsx_artifact_id,
      filename: d.xlsx_filename,
      label: "XLSX",
    });
  if (d.docx_artifact_id)
    links.push({
      artifactId: d.docx_artifact_id,
      filename: d.docx_filename,
      label: "DOCX",
    });
  return links;
}

export function DocumentsList({
  items,
}: {
  items: ClientDeliverable[];
}): JSX.Element {
  const columns: DataTableColumn<ClientDeliverable>[] = [
    {
      key: "service",
      header: "Service",
      cell: (d) => (
        <span className="font-medium text-ink-primary">{serviceLabel(d)}</span>
      ),
    },
    {
      key: "title",
      header: "Document",
      cell: (d) => (
        <div className="min-w-0">
          <p className="text-ink-primary">{d.title}</p>
          {d.summary ? (
            <p className="mt-0.5 max-w-prose text-xs text-ink-tertiary">
              {d.summary}
            </p>
          ) : null}
        </div>
      ),
    },
    {
      key: "version",
      header: "Version",
      align: "center",
      cell: (d) => <span className="tabular-nums">v{d.version}</span>,
    },
    {
      key: "released",
      header: "Released",
      cell: (d) => (
        <span className="whitespace-nowrap text-ink-secondary">
          {formatReleased(d.released_at)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (d) =>
        d.superseded ? (
          <StatusPill tone="warning">Superseded</StatusPill>
        ) : (
          <StatusPill tone="success">Final</StatusPill>
        ),
    },
    {
      key: "downloads",
      header: "Download",
      cell: (d) => {
        const links = downloadsFor(d);
        if (links.length === 0) {
          return <span className="text-xs text-ink-tertiary">—</span>;
        }
        const dashboardPath = dashboardPathFor(d);
        return (
          <div className="flex flex-wrap gap-2">
            {dashboardPath ? (
              <a
                href={dashboardPath}
                className="rounded-md border border-brand-600 px-2.5 py-1 text-xs font-semibold text-brand-600 hover:bg-surface-sunken"
              >
                View dashboard
              </a>
            ) : null}
            {links.map((l) => (
              <a
                key={l.artifactId}
                href={`/api/proxy/artifacts/${l.artifactId}/download`}
                className="rounded-md border border-border px-2.5 py-1 text-xs font-semibold text-brand-600 hover:bg-surface-sunken"
                {...(l.filename ? { download: l.filename } : {})}
              >
                {l.label}
              </a>
            ))}
          </div>
        );
      },
    },
  ];

  return (
    <DataTable
      caption="Reports and workbooks released to your organization."
      columns={columns}
      rows={items}
      rowKey={(d) => d.id}
      emptyState={
        <EmptyState
          title="No documents yet"
          description="When your SHIELD analyst releases a report, it will appear here to view and download."
        />
      }
    />
  );
}
