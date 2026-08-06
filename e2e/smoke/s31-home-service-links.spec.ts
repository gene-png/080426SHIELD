import { expect, test } from "@playwright/test";

import { signIn } from "../helpers/auth";

/**
 * Issue 1: the /home "Your services" grid rendered each service as a plain card
 * with no link, so a client could see a service but had no way to open it —
 * exactly the dead end Navigation_Spec §12 forbids.
 *
 * Every card is now a link whose destination mirrors that card's own phase:
 *   "Report ready"  → that service's dashboard (or /results when the service
 *                     kind has no dashboard, e.g. NIST CSF)
 *   "In progress"   → the self-assessment questionnaire to resume
 *   anything else   → /assessments
 *
 * Runs against the seeded Atlas tenant, which carries services in several
 * phases at once. The assertions are phase-driven rather than name-driven so
 * they survive the shared DB accumulating more seeded services over time.
 */

const CLIENT_EMAIL = "client@atlas.example";
const CLIENT_PASSWORD = "DemoPass!2026";

/** Finding #17: the one named primary action each bucket's cards must carry. */
const ACTION_FOR: Record<string, string> = {
  "Action required": "Resume assessment",
  "In progress": "View status",
  "Results available": "View results",
};

test("client home: every service card is a link, routed by its own phase", async ({
  page,
}) => {
  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto("/home");

  const heading = page.getByRole("heading", { name: "Your services" });
  await expect(heading).toBeVisible();

  // The grid is the <ul> that follows the section heading.
  const cards = page.locator("section", { has: heading }).locator("li");
  const count = await cards.count();
  expect(
    count,
    "seeded tenant should expose at least one service",
  ).toBeGreaterThan(0);

  let sawReportReady = false;
  let sawInProgress = false;

  for (let i = 0; i < count; i++) {
    const card = cards.nth(i);
    const link = card.getByRole("link").first();

    // 1. No dead ends: every card is a link with a real in-app destination.
    await expect(link, `card ${i} must be a link`).toHaveAttribute(
      "href",
      /^\/\S+/,
    );

    const href = (await link.getAttribute("href")) ?? "";
    const text = (await card.innerText()).toLowerCase();

    // 2. The destination matches the phase the card advertises.
    if (text.includes("report ready")) {
      sawReportReady = true;
      expect(
        href,
        `a "Report ready" card must open a dashboard or the results list (got ${href})`,
      ).toMatch(/^\/(dashboards\/(attack|zt|tech-debt)\/|results)/);
    } else if (text.includes("in progress")) {
      sawInProgress = true;
      expect(
        href,
        `an "In progress" card must resume the self-assessment (got ${href})`,
      ).toMatch(/^\/self-assessment\//);
    }
  }

  // The seeded tenant carries both phases; if it stops doing so the routing
  // above would silently go unexercised, so pin that too.
  expect(sawReportReady, "seed should include a released service").toBe(true);
  expect(sawInProgress, "seed should include an in-progress service").toBe(
    true,
  );
});

/**
 * C3: the grid is grouped by who owns the next move — Action required / In
 * progress / Results available — and a service belongs to EXACTLY ONE group.
 *
 * The cross-bucket duplicate check compares whole-card text, not titles, and
 * tolerates repeats WITHIN a bucket on purpose: titles are not unique on the
 * shared e2e database (s29 mints "E2E Software Portfolio" every run), so two
 * same-named services in the same phase are expected and legitimate. Landing in
 * two different buckets is the defect worth catching.
 */
test("client home: services are grouped by task status, one bucket each", async ({
  page,
}) => {
  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto("/home");

  const heading = page.getByRole("heading", { name: "Your services" });
  await expect(heading).toBeVisible();
  const services = page.locator("section", { has: heading });

  const buckets = services.locator("section[aria-labelledby^='bucket-']");
  const bucketCount = await buckets.count();
  expect(
    bucketCount,
    "the seeded tenant should fill at least one task-status bucket",
  ).toBeGreaterThan(0);

  // Whole-card text -> the bucket index it was found in.
  const placed = new Map<string, number>();
  let carded = 0;

  for (let i = 0; i < bucketCount; i++) {
    const group = buckets.nth(i);
    // textContent, not innerText: the heading is styled `uppercase`, and
    // innerText returns the CSS-transformed "ACTION REQUIRED". The DOM text is
    // what the accessible name is computed from, so it is also what a screen
    // reader announces — assert against that rather than against the styling.
    const title = (
      (await group.getByRole("heading").first().textContent()) ?? ""
    )
      .replace(/\s+/g, " ")
      .trim();
    expect(
      title,
      "a bucket heading must name a task status and carry its count",
    ).toMatch(/^(Action required|In progress|Results available) \(\d+\)$/);

    // The count in the heading must describe what the bucket actually lists —
    // service cards plus the unread-messages row, which needs the client too
    // but has no service card of its own.
    const declared = Number(/\((\d+)\)/.exec(title)?.[1]);
    const cards = group.locator("li");
    const cardCount = await cards.count();
    const messageRows = await group
      .getByRole("link", { name: /Open messages/ })
      .count();
    expect(
      declared,
      `"${title}" must count what it lists (${cardCount} cards + ${messageRows} message rows)`,
    ).toBe(cardCount + messageRows);

    // Finding #17: every card names its one primary action, and the wording
    // matches the bucket it sits in.
    const expectedAction = ACTION_FOR[title.replace(/ \(\d+\)$/, "")];
    expect(expectedAction, `unmapped bucket heading "${title}"`).toBeTruthy();

    carded += cardCount;
    for (let j = 0; j < cardCount; j++) {
      const text = (await cards.nth(j).innerText()).trim();
      expect(
        text,
        `a card in "${title}" must name its action ("${expectedAction}")`,
      ).toContain(expectedAction);
      const already = placed.get(text);
      expect(
        already === undefined || already === i,
        `a service must sit in exactly one bucket, but this one is in ${already} and ${i}:\n${text}`,
      ).toBe(true);
      placed.set(text, i);
    }
  }

  // Nothing left behind in an ungrouped flat grid.
  expect(carded, "every service card must live inside a bucket").toBe(
    await services.locator("li").count(),
  );
});

test("client home: a released service card actually opens its dashboard", async ({
  page,
}) => {
  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto("/home");

  const heading = page.getByRole("heading", { name: "Your services" });
  await expect(heading).toBeVisible();

  // First card whose link points at a dashboard route.
  const dashboardLink = page
    .locator("section", { has: heading })
    .locator('li a[href^="/dashboards/"]')
    .first();
  await expect(dashboardLink).toBeVisible();
  const href = await dashboardLink.getAttribute("href");

  await dashboardLink.click();

  await expect
    .poll(() => new URL(page.url()).pathname, {
      message: "clicking a released service card must land on its dashboard",
      timeout: 30_000,
    })
    .toBe(href);

  // And the dashboard actually rendered rather than the not-available fallback.
  await expect(
    page.getByRole("heading", { name: "Dashboard not available yet" }),
  ).toHaveCount(0);
});
