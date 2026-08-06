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
