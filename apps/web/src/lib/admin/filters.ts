import { SERVICE_LABELS, type ServiceType } from "@/lib/intake/types";

import type { AdminServiceRequestRow } from "./types";

/**
 * Intake-queue filtering (IA appendix: "Filters by client, service, status,
 * and age").
 *
 * Pure predicates, kept out of the components for two reasons: they are
 * testable without rendering, and the empty-state message reads from the SAME
 * definition of "what is active" as the filtering does. A filtered list that
 * says "no results" without naming the filter reads as "no work exists", which
 * is the opposite of the truth and the exact way a queue hides work.
 *
 * Everything here runs client-side over data the components have already
 * fetched — no API change, no extra round trip.
 */

export type RequestStatus = "awaiting" | "published" | "declined";
export type AgeBucket = "all" | "week" | "month" | "older";

export interface RequestFilters {
  /** A ServiceType, or "all". */
  service: string;
  status: RequestStatus | "all";
  age: AgeBucket;
}

export const DEFAULT_REQUEST_FILTERS: RequestFilters = {
  service: "all",
  status: "all",
  age: "all",
};

const STATUS_LABELS: Record<RequestStatus, string> = {
  awaiting: "Awaiting review",
  published: "Workspace created",
  declined: "Declined",
};

const AGE_LABELS: Record<Exclude<AgeBucket, "all">, string> = {
  week: "Last 7 days",
  month: "8–30 days",
  older: "More than 30 days",
};

export const REQUEST_STATUS_OPTIONS: ReadonlyArray<{
  value: RequestStatus;
  label: string;
}> = (Object.keys(STATUS_LABELS) as RequestStatus[]).map((value) => ({
  value,
  label: STATUS_LABELS[value],
}));

export const AGE_OPTIONS: ReadonlyArray<{
  value: Exclude<AgeBucket, "all">;
  label: string;
}> = (Object.keys(AGE_LABELS) as Exclude<AgeBucket, "all">[]).map((value) => ({
  value,
  label: AGE_LABELS[value],
}));

/**
 * A request's position in the queue.
 *
 * Declined wins over fulfilled: a declined request is closed, and showing it
 * under "workspace created" would put dead work back in front of a consultant.
 */
export function requestStatusOf(row: AdminServiceRequestRow): RequestStatus {
  if (row.declined_at) return "declined";
  if (row.fulfilled_service_id) return "published";
  return "awaiting";
}

/**
 * Which age bucket a request falls in.
 *
 * A timestamp in the future counts as newest rather than oldest — clock skew
 * between boxes is real, and burying a just-arrived request under "more than 30
 * days" would hide the freshest work on the page.
 */
export function ageBucketOf(
  requestedAt: string,
  now: Date,
): Exclude<AgeBucket, "all"> {
  const at = new Date(requestedAt).getTime();
  if (Number.isNaN(at)) return "older";
  const days = (now.getTime() - at) / (24 * 60 * 60 * 1000);
  if (days <= 7) return "week";
  if (days <= 30) return "month";
  return "older";
}

export function filterServiceRequests(
  rows: AdminServiceRequestRow[],
  filters: RequestFilters,
  now: Date,
): AdminServiceRequestRow[] {
  return rows.filter((row) => {
    if (filters.service !== "all" && row.service_type !== filters.service) {
      return false;
    }
    if (filters.status !== "all" && requestStatusOf(row) !== filters.status) {
      return false;
    }
    if (
      filters.age !== "all" &&
      ageBucketOf(row.requested_at, now) !== filters.age
    ) {
      return false;
    }
    return true;
  });
}

/** Human-readable names of the active filters, for the empty state. */
export function activeFilterLabels(filters: RequestFilters): string[] {
  const out: string[] = [];
  if (filters.service !== "all") {
    out.push(SERVICE_LABELS[filters.service as ServiceType] ?? filters.service);
  }
  if (filters.status !== "all") out.push(STATUS_LABELS[filters.status]);
  if (filters.age !== "all") out.push(AGE_LABELS[filters.age]);
  return out;
}

// --- Organization index -----------------------------------------------------

export interface OrgFilters {
  query: string;
  /** Only organizations that still have requests awaiting review. */
  awaitingOnly: boolean;
}

export const DEFAULT_ORG_FILTERS: OrgFilters = {
  query: "",
  awaitingOnly: false,
};

/** Minimal shape needed to filter the org index — anything wider also works. */
interface OrgLike {
  legal_name: string;
  open_request_count: number;
}

export function filterOrganizations<T extends OrgLike>(
  orgs: T[],
  filters: OrgFilters,
): T[] {
  const q = filters.query.trim().toLowerCase();
  return orgs.filter((org) => {
    if (q && !org.legal_name.toLowerCase().includes(q)) return false;
    if (filters.awaitingOnly && org.open_request_count <= 0) return false;
    return true;
  });
}
