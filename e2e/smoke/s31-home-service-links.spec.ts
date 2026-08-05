import { expect, test } from "@playwright/test";

import { signIn } from "../helpers/auth";

/**
 * Issue 1: the /home "Your services" grid rendered each service as a plain card
 * with no link, so a client could see a service but had no way to open it —
 * exactly the dead end Navigation_Spec §12 forbids.
 *
 * Every card is now a link whose destination mirrors that card's own phase:
 *   "Report ready"  → that service's dashboard (or /documents when the service
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
        `a "Report ready" card must open a dashboard or the documents list (got ${href})`,
      ).toMatch(/^\/(dashboards\/(attack|zt|tech-debt)\/|documents)/);
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
