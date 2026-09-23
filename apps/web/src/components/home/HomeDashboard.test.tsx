import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HomeDashboard, type HomePanel } from "./HomeDashboard";

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
        unavailable={[]}
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
        unavailable={[]}
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
        unavailable={[]}
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
        unavailable={[]}
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
        unavailable={[]}
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

  /**
   * Finding #17's other half: "give each service one primary action, such as
   * Resume assessment, View status, or View results." The bucket says who owns
   * the next move; the action names what that move IS, in the client's words.
   *
   * The action must stay INSIDE the card's existing link rather than becoming a
   * link of its own — a nested <a> is invalid HTML and would give every card two
   * tab stops pointing at the same place.
   */
  it.each([
    ["Action required", "NIST CSF", "Resume assessment"],
    ["In progress", "Zero Trust", "View status"],
    ["Results available", "Tech Debt Review", "View results"],
  ] as const)("names the primary action in %s", (bucketName, title, action) => {
    renderAll();
    const card = within(bucket(bucketName))
      .getAllByRole("listitem")
      .find((li) => li.textContent?.includes(title)) as HTMLElement;
    expect(card, `no card titled ${title}`).toBeTruthy();
    expect(
      within(card).getByText(action, { exact: false }),
    ).toBeInTheDocument();
  });

  it("keeps each card a single tab stop — the action is not its own link", () => {
    renderAll();
    for (const b of BUCKETS) {
      for (const li of within(bucket(b)).getAllByRole("listitem")) {
        expect(
          within(li).getAllByRole("link"),
          "a card must expose exactly one link, not a nested action anchor",
        ).toHaveLength(1);
      }
    }
  });

  it("still shows the no-services empty state", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[]}
        engagements={[]}
        unreadMessages={0}
        valueSummary={null}
        unavailable={[]}
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

describe("HomeDashboard — a failed panel is not an empty one (#236)", () => {
  /**
   * The page used to fetch four endpoints in one `Promise.all` with no `catch`,
   * and there is no `error.tsx` anywhere under `apps/web/src/app` — so any one
   * rejection took the WHOLE page down, including the client's released
   * reports, which have nothing to do with the endpoint that failed.
   *
   * `allSettled` alone is only half the fix. Passing `[]` / `0` / `null` for a
   * panel that ERRORED makes the page assert "you have no engagements" and
   * "no unread messages" — claims about the client's account, made from a
   * failure. Missing data defaults to UNCONFIRMED, never to confirmed.
   */
  it("says engagements could not be loaded instead of claiming there are none", () => {
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[deliverable({})]}
        engagements={[]}
        unreadMessages={0}
        valueSummary={null}
        unavailable={["engagements"]}
      />,
    );

    expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument();
    // The EMPTY-state copy must NOT also be on screen, or "failed" and "empty"
    // are still indistinguishable. The needle is the component's actual string:
    // an earlier version of this line looked for "no engagements yet", which
    // appears nowhere in the component under any input, so it passed in the
    // fixed and the unfixed world alike -- the #72 shape, inside the test whose
    // whole purpose is to prove these two states are distinguishable.
    expect(screen.queryByText(/no services yet/i)).toBeNull();
  });

  // DERIVED, AND THE FIRST VERSION OF THIS WAS NOT.
  //
  // It was `const ALL_PANELS: HomePanel[] = [...]` with a comment claiming a
  // fifth union member would be a type error. That is false: `HomePanel[]` is
  // satisfied by any SUBSET, so adding "notifications" to the union left the
  // array assignable, tsc green, and this test green over four panels with the
  // fifth unwired. It re-enumerated exactly what it claimed to derive, and I
  // had cited it as the countermeasure against that class of mistake.
  //
  // A TOTAL RECORD is the derived form: omit a key and `Record<HomePanel, true>`
  // is TS2741 before any test runs.
  const PANEL_COVERAGE: Record<HomePanel, true> = {
    deliverables: true,
    engagements: true,
    messages: true,
    value: true,
  };
  const ALL_PANELS = Object.keys(PANEL_COVERAGE) as HomePanel[];

  it.each(ALL_PANELS)(
    "says %s could not be loaded rather than rendering it as absent",
    (panel) => {
      render(
        <HomeDashboard
          greetingName="Ada"
          deliverables={[]}
          engagements={[]}
          unreadMessages={0}
          valueSummary={null}
          unavailable={[panel]}
        />,
      );
      // getAllByText, not getByText: a panel may disclose on MORE THAN ONE
      // surface -- deliverables says so in both the hero and Recent activity --
      // and `getByText` throws on multiple matches, so the single-match form
      // goes red the moment a SECOND surface starts telling the truth.
      expect(
        screen.getAllByText(/could not be loaded/i).length,
      ).toBeGreaterThan(0);
    },
  );

  it("discloses a deliverables failure on BOTH surfaces that would otherwise claim absence", () => {
    /**
     * The `it.each` above asserts one disclosure per panel, so it is blind to a
     * SECOND surface still lying — which is exactly what happened: the hero was
     * guarded and "Recent activity" was not, so the page said "Your reports
     * could not be loaded" and, directly beneath it, "Released reports will
     * show up here as your engagement progresses." to a client with three.
     *
     * Disabling the Recent-activity guard left all 699 tests green until this
     * existed. Both needles are asserted separately because the whole defect
     * was one surface disclosing and the other not.
     */
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[]}
        engagements={[]}
        unreadMessages={0}
        valueSummary={null}
        unavailable={["deliverables"]}
      />,
    );

    // The hero.
    expect(
      screen.getByText(/your reports could not be loaded/i),
    ).toBeInTheDocument();
    // Recent activity, which is the one that was missing.
    expect(
      screen.getByText(/your released reports could not be loaded/i),
    ).toBeInTheDocument();
    // And neither surface claims the client has none.
    expect(
      screen.queryByText(/released reports will show up here/i),
    ).toBeNull();
  });

  it("still renders the value card when the summary loaded fine", () => {
    // The other half of the `value` branch. The it.each above covers its
    // FAILURE state; without this, deleting the whole `down.has("value")`
    // block -- or rendering the could-not-load copy unconditionally -- stays
    // green while the card never appears.
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[]}
        engagements={[]}
        unreadMessages={0}
        valueSummary={{
          tech_debt_savings_usd: null,
          tech_debt_savings_cost_known: true,
          tech_debt_savings_unresolved: false,
          zt_gap_count: null,
          zt_gap_unresolved: false,
          zt_services: 0,
          zt_targets_defaulted: null,
          zt_targets_unusable: null,
          zt_targets_computed_live: null,
          attack_uncovered_count: null,
          attack_uncovered_unresolved: false,
          csf_gap_count: null,
          csf_gap_unresolved: false,
          csf_services: 0,
          csf_targets_defaulted: null,
          csf_targets_unusable: null,
          csf_targets_computed_live: null,
          has_any_data: true,
          has_unresolved: false,
        }}
        unavailable={[]}
      />,
    );
    // ASSERT THE CARD, not just the absence of the error copy. The first
    // version used a fixture with `has_any_data: false`, and `ValueLoopCard`
    // opens `if (!summary.has_any_data && !summary.has_unresolved) return null`
    // -- so the card rendered NOTHING and the test could not fail for the
    // reason its name gives, while its comment said "without this the card
    // never appears" about a case in which the card never appears.
    expect(
      // The card's TITLE specifically -- the same phrase also appears in the
      // page subtitle, so a bare text match is ambiguous.
      screen.getByRole("heading", { name: /your engagement at a glance/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/could not be loaded/i)).toBeNull();
  });

  it("still claims nothing when engagements are genuinely empty", () => {
    // The other half of the branch. Without this, a "fix" that renders the
    // could-not-load copy unconditionally passes the test above and lies in
    // the ordinary empty case.
    render(
      <HomeDashboard
        greetingName="Ada"
        deliverables={[deliverable({})]}
        engagements={[]}
        unreadMessages={0}
        valueSummary={null}
        unavailable={[]}
      />,
    );

    expect(screen.queryByText(/could not be loaded/i)).toBeNull();
  });
});
