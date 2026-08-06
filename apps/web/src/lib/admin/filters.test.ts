import { describe, expect, it } from "vitest";

import {
  DEFAULT_REQUEST_FILTERS,
  activeFilterLabels,
  filterOrganizations,
  filterServiceRequests,
  requestStatusOf,
  type OrgFilters,
  type RequestFilters,
} from "./filters";

import type { AdminServiceRequestRow } from "./types";

/**
 * IA appendix: "Filters by client, service, status, and age."
 *
 * The predicates live here rather than inside the components so they are
 * testable without rendering, and so the empty-state message and the filtering
 * itself read from the SAME definition of "what is active" — a filtered list
 * that says "no results" without naming the filter reads as "no work exists",
 * which is the opposite of the truth.
 */

const NOW = new Date("2026-08-06T12:00:00Z");

function daysAgo(n: number): string {
  return new Date(NOW.getTime() - n * 24 * 60 * 60 * 1000).toISOString();
}

function req(over: Partial<AdminServiceRequestRow>): AdminServiceRequestRow {
  return {
    id: "r1",
    service_type: "nist_csf",
    requested_at: daysAgo(1),
    requested_by: {
      id: "u1",
      email: "a@example.com",
      display_name: "A",
      role: "client",
    } as AdminServiceRequestRow["requested_by"],
    notes: null,
    deadline: null,
    csf_target_tier: null,
    csf_profile: null,
    zt_target_stage: null,
    fulfilled_service_id: null,
    declined_at: null,
    declined_reason: null,
    ...over,
  };
}

function filters(over: Partial<RequestFilters> = {}): RequestFilters {
  return { ...DEFAULT_REQUEST_FILTERS, ...over };
}

describe("requestStatusOf", () => {
  it("reports a declined request as declined even once fulfilled", () => {
    expect(
      requestStatusOf(
        req({ declined_at: daysAgo(1), fulfilled_service_id: "s1" }),
      ),
    ).toBe("declined");
  });

  it("reports a fulfilled request as published", () => {
    expect(requestStatusOf(req({ fulfilled_service_id: "s1" }))).toBe(
      "published",
    );
  });

  it("reports an untouched request as awaiting", () => {
    expect(requestStatusOf(req({}))).toBe("awaiting");
  });
});

describe("filterServiceRequests", () => {
  const rows = [
    req({ id: "csf-new", service_type: "nist_csf", requested_at: daysAgo(2) }),
    req({
      id: "zt-old",
      service_type: "zero_trust_cisa",
      requested_at: daysAgo(60),
    }),
    req({
      id: "td-published",
      service_type: "tech_debt",
      requested_at: daysAgo(10),
      fulfilled_service_id: "s9",
    }),
  ];

  it("returns everything by default", () => {
    expect(filterServiceRequests(rows, filters(), NOW)).toHaveLength(3);
  });

  it("filters by service type", () => {
    const out = filterServiceRequests(
      rows,
      filters({ service: "nist_csf" }),
      NOW,
    );
    expect(out.map((r) => r.id)).toEqual(["csf-new"]);
  });

  it("filters by status", () => {
    const out = filterServiceRequests(
      rows,
      filters({ status: "published" }),
      NOW,
    );
    expect(out.map((r) => r.id)).toEqual(["td-published"]);
  });

  it.each([
    ["week", ["csf-new"]],
    ["month", ["td-published"]],
    ["older", ["zt-old"]],
  ] as const)("filters by age bucket %s", (age, expected) => {
    const out = filterServiceRequests(rows, filters({ age }), NOW);
    expect(out.map((r) => r.id)).toEqual(expected);
  });

  it("combines filters rather than treating them as alternatives", () => {
    const out = filterServiceRequests(
      rows,
      filters({ service: "nist_csf", status: "published" }),
      NOW,
    );
    expect(out).toEqual([]);
  });

  it("treats a request dated in the future as newest, not as older", () => {
    // Clock skew between boxes is real; a future timestamp must not silently
    // fall into "more than 30 days ago".
    const future = [req({ id: "future", requested_at: daysAgo(-3) })];
    expect(
      filterServiceRequests(future, filters({ age: "week" }), NOW),
    ).toHaveLength(1);
    expect(
      filterServiceRequests(future, filters({ age: "older" }), NOW),
    ).toHaveLength(0);
  });
});

describe("activeFilterLabels", () => {
  it("is empty when nothing is filtered", () => {
    expect(activeFilterLabels(filters())).toEqual([]);
  });

  it("names each active filter so an empty result can explain itself", () => {
    const labels = activeFilterLabels(
      filters({ service: "tech_debt", status: "awaiting", age: "week" }),
    );
    expect(labels).toHaveLength(3);
    expect(labels.join(" ")).toContain("Technical Debt Review");
    expect(labels.join(" ")).toContain("Awaiting review");
    expect(labels.join(" ")).toContain("Last 7 days");
  });
});

describe("filterOrganizations", () => {
  const orgs = [
    { legal_name: "Atlas Defense", open_request_count: 2 },
    { legal_name: "Borealis Grid", open_request_count: 0 },
  ];

  function orgFilters(over: Partial<OrgFilters> = {}): OrgFilters {
    return { query: "", awaitingOnly: false, ...over };
  }

  it("matches a name case-insensitively on a substring", () => {
    expect(
      filterOrganizations(orgs, orgFilters({ query: "atl" })).map(
        (o) => o.legal_name,
      ),
    ).toEqual(["Atlas Defense"]);
  });

  it("ignores surrounding whitespace in the query", () => {
    expect(
      filterOrganizations(orgs, orgFilters({ query: "  borealis " })),
    ).toHaveLength(1);
  });

  it("narrows to organizations that still owe review", () => {
    expect(
      filterOrganizations(orgs, orgFilters({ awaitingOnly: true })).map(
        (o) => o.legal_name,
      ),
    ).toEqual(["Atlas Defense"]);
  });
});
