import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeDashboard } from "./HomeDashboard";

import type { ClientDeliverable } from "@/components/results/ResultsList";
import type { AssessmentResponse } from "@/lib/intake/types";

/**
 * Issue 1: the "Your services" grid rendered plain cards with no link, so a
 * client could see a service but had no way to open it — the dead-end the
 * Navigation_Spec §12 forbids. These tests pin the contract: EVERY service card
 * is a link, and its destination follows that card's own phase.
 */

const SVC_RELEASED = "11111111-1111-4111-8111-111111111111";
const SVC_DRAFT = "22222222-2222-4222-8222-222222222222";
const SVC_REVIEW = "33333333-3333-4333-8333-333333333333";

/** The three task-status buckets, in the order /home renders them (C3). */
const BUCKETS = [
  "Action required",
  "In progress",
  "Results available",
] as const;

function engagement(over: Partial<AssessmentResponse>): AssessmentResponse {
  return {
    service_id: SVC_DRAFT,
    service_type: "nist_csf",
    title: "Untitled",
    status: "active",
    assessment_status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function deliverable(over: Partial<ClientDeliverable>): ClientDeliverable {
  return {
    id: "d1",
    service_id: SVC_RELEASED,
    service_kind: "tech_debt",
    service_title: "Tech Debt",
    title: "Report",
    summary: null,
    version: 1,
    released_at: "2026-02-02T00:00:00Z",
    superseded: false,
    pdf_artifact_id: null,
    xlsx_artifact_id: null,
    docx_artifact_id: null,
    pdf_filename: null,
    xlsx_filename: null,
    docx_filename: null,
    ...over,
  };
}

/**
 * Accessible name of a bucket heading. The count is rendered INSIDE the
 * heading — a screen-reader user should hear "Action required, 2" rather than
 * meet a bare label and have to count cards — so the name is "Action required
 * (2)", not "Action required". Anchored at both ends so this stays an exact
 * match on the title plus an optional count, not a loose substring.
 */
function headingName(name: (typeof BUCKETS)[number]): RegExp {
  return new RegExp(`^${name} \\(\\d+\\)$`);
}

/**
 * The bucket group with this heading. Throws if it isn't rendered, so an
 * assertion about "which bucket is this service in" can never quietly pass by
 * looking in a group that doesn't exist.
 */
function bucket(name: (typeof BUCKETS)[number]): HTMLElement {
  return screen
    .getByRole("heading", { name: headingName(name) })
    .closest("section") as HTMLElement;
}

/**
 * Titles of the service cards inside one bucket, in render order.
 *
 * Identified by the title the client actually reads rather than by href: a
 * submitted assessment links to the generic /assessments list, so its card
 * carries no service id anywhere in the DOM.
 */
function titlesIn(name: (typeof BUCKETS)[number]): string[] {
  return within(bucket(name))
    .getAllByRole("listitem")
    .map((li) => li.querySelector("p")?.textContent ?? "");
}

/** The <li> for a given service id inside the "Your services" grid. */
function serviceCard(serviceId: string): HTMLElement {
  const grid = screen.getByRole("heading", { name: "Your services" })
    .parentElement as HTMLElement;
  const item = within(grid)
    .getAllByRole("listitem")
    .find((li) => li.querySelector(`a[href*="${serviceId}"]`) !== null);
  // Fall back to positional lookup so the assertion failure is about the href,
  // not a missing element, while the feature is unimplemented.
  return item ?? (within(grid).getAllByRole("listitem")[0] as HTMLElement);
}

describe("HomeDashboard — service card links (issue 1)", () => {
  it("links a released service card to its dashboard", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[deliverable({})]}
        engagements={[
          engagement({
            service_id: SVC_RELEASED,
            service_type: "tech_debt",
            title: "Tech Debt Review",
            assessment_status: null,
          }),
        ]}
        unreadMessages={0}
        valueSummary={null}
      />,
    );
    const card = serviceCard(SVC_RELEASED);
    const link = within(card).getByRole("link");
    expect(link).toHaveAttribute(
      "href",
      `/dashboards/tech-debt/${SVC_RELEASED}`,
    );
  });

  it("links an in-progress self-assessment card to the questionnaire", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[]}
        engagements={[
          engagement({
            service_id: SVC_DRAFT,
            service_type: "nist_csf",
            title: "NIST CSF",
            assessment_status: "draft",
          }),
        ]}
        unreadMessages={0}
        valueSummary={null}
      />,
    );
    const card = serviceCard(SVC_DRAFT);
    const link = within(card).getByRole("link");
    expect(link).toHaveAttribute(
      "href",
      `/self-assessment/${SVC_DRAFT}?type=nist_csf`,
    );
  });

  it("gives every service card a link — no card is a dead end", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[deliverable({})]}
        engagements={[
          engagement({
            service_id: SVC_RELEASED,
            service_type: "tech_debt",
            assessment_status: null,
          }),
          engagement({ service_id: SVC_DRAFT, assessment_status: "draft" }),
          engagement({
            service_id: SVC_REVIEW,
            service_type: "attack_coverage",
            assessment_status: "submitted",
          }),
        ]}
        unreadMessages={0}
        valueSummary={null}
      />,
    );
    const grid = screen.getByRole("heading", { name: "Your services" })
      .parentElement as HTMLElement;
    const items = within(grid).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    for (const li of items) {
      const link = within(li).queryByRole("link");
      expect(link, "every service card must be a link").not.toBeNull();
      expect(link).toHaveAttribute("href", expect.stringMatching(/^\/\S+/));
    }
  });
});

/**
 * C3: "Your services" was one flat grid in arrival order, so a client with
 * several engagements had to read every phase pill to work out which one needed
 * them — and an open self-assessment appeared TWICE, once as a card and again
 * in the "Waiting on you" list.
 *
 * The grid is now grouped by who owns the next move. Each service lands in
 * EXACTLY ONE bucket, which is what kills the duplication: there is one place
 * to look for "what needs me", not three.
 *
 * Deliberately NOT tested here because it is deliberately unchanged: the phase
 * pill wording. The bucket says who owns the move, the pill says what phase the
 * engagement is in. Both are true at once, and s31 routes off the pill text.
 */
describe("HomeDashboard — task-status buckets (C3)", () => {
  const threeServices = [
    engagement({
      service_id: SVC_RELEASED,
      service_type: "tech_debt",
      title: "Tech Debt Review",
      assessment_status: null,
    }),
    engagement({
      service_id: SVC_DRAFT,
      service_type: "nist_csf",
      title: "NIST CSF",
      assessment_status: "draft",
    }),
    engagement({
      service_id: SVC_REVIEW,
      service_type: "zero_trust_cisa",
      title: "Zero Trust",
      assessment_status: "submitted",
    }),
  ];

  function renderAll(unreadMessages = 0) {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[deliverable({})]}
        engagements={threeServices}
        unreadMessages={unreadMessages}
        valueSummary={null}
      />,
    );
  }

  it("files an open self-assessment under Action required", () => {
    renderAll();
    expect(titlesIn("Action required")).toEqual(["NIST CSF"]);
  });

  it("files a submitted assessment under In progress — the analyst owns it", () => {
    renderAll();
    expect(titlesIn("In progress")).toEqual(["Zero Trust"]);
  });

  it("files a service with a released report under Results available", () => {
    renderAll();
    expect(titlesIn("Results available")).toEqual(["Tech Debt Review"]);
  });

  it("puts every service in exactly one bucket — no service appears twice", () => {
    renderAll();
    const all = BUCKETS.flatMap((b) => titlesIn(b));
    expect(all).toHaveLength(threeServices.length);
    expect(new Set(all).size).toBe(threeServices.length);
  });

  it("omits a bucket that has nothing in it", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[]}
        engagements={[engagement({ service_id: SVC_DRAFT })]}
        unreadMessages={0}
        valueSummary={null}
      />,
    );
    expect(
      screen.getByRole("heading", { name: headingName("Action required") }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: headingName("Results available") }),
      "an empty bucket must not render an empty heading",
    ).toBeNull();
  });

  it("raises unread messages inside Action required, not in a second list", () => {
    renderAll(3);
    expect(
      within(bucket("Action required")).getByRole("link", {
        name: /open messages/i,
      }),
    ).toHaveAttribute("href", "/messages");
    expect(
      screen.queryByText("Waiting on you"),
      "the separate waiting-on-you list is what duplicated the self-assessment",
    ).toBeNull();
  });

  it("still shows the no-services empty state", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[]}
        engagements={[]}
        unreadMessages={0}
        valueSummary={null}
      />,
    );
    expect(screen.getByText("No services yet")).toBeInTheDocument();
    for (const b of BUCKETS) {
      expect(
        screen.queryByRole("heading", { name: headingName(b) }),
      ).toBeNull();
    }
  });
});
