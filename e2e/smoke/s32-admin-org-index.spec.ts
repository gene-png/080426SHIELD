import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * Issue 7: /admin/queue used to open straight onto ONE organization.
 *
 * `GET /admin/intake-queue` without a `client_id` returns every tenant's
 * service requests but sets the `client` field to whichever tenant was created
 * most recently — its own docstring calls that "advisory". The page rendered
 * that advisory tenant as its Organization header, so an admin saw one client's
 * profile stapled above every client's work, which read as "the queue opens to
 * the last client that submitted".
 *
 * The queue is now an index of organizations; each one opens its own page with
 * its intake details at the top and its pending work below.
 */

test("admin queue is an organization index, and each org opens its own scoped page", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/queue");

  await expect(
    page.getByRole("heading", { name: "Intake queue", level: 1 }),
  ).toBeVisible();

  // The landing page lists organizations as links, and does NOT render a single
  // tenant's intake profile (the old behaviour).
  const orgLinks = page.locator('a[href^="/admin/queue/"]');
  await expect(orgLinks.first()).toBeVisible();
  const orgCount = await orgLinks.count();
  expect(
    orgCount,
    "seeded stack should expose at least one org",
  ).toBeGreaterThan(0);

  // The org index must not itself show the per-org intake sections.
  await expect(page.getByRole("heading", { name: "Organization" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("heading", { name: /^Service requests \(/ }),
  ).toHaveCount(0);

  // Open the first organization.
  const href = await orgLinks.first().getAttribute("href");
  await orgLinks.first().click();

  await expect
    .poll(() => new URL(page.url()).pathname, {
      message: "clicking an organization opens its scoped queue page",
      timeout: 30_000,
    })
    .toBe(href);

  // The scoped page shows that org's work and a way back — no dead end.
  await expect(
    page.getByRole("heading", { name: /^Service requests \(/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "← All organizations" }),
  ).toBeVisible();
});

test("scoped queue pages for two different orgs show different organizations", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/queue");

  const orgLinks = page.locator('a[href^="/admin/queue/"]');
  await expect(orgLinks.first()).toBeVisible();
  const count = await orgLinks.count();
  test.skip(count < 2, "needs at least two tenants to prove scoping");

  const hrefs = await orgLinks.evaluateAll((els) =>
    els.map((e) => (e as HTMLAnchorElement).getAttribute("href") ?? ""),
  );

  // The page H1 is the organization's legal name once intake exists; at minimum
  // the two pages must not render identical content, which is exactly what the
  // old advisory-client behaviour did.
  await page.goto(hrefs[0]);
  await expect(
    page.getByRole("heading", { name: /^Service requests \(/ }),
  ).toBeVisible();
  const firstHeading = await page
    .getByRole("heading", { level: 1 })
    .first()
    .innerText();

  await page.goto(hrefs[1]);
  await expect(
    page.getByRole("heading", { name: /^Service requests \(/ }),
  ).toBeVisible();
  const secondHeading = await page
    .getByRole("heading", { level: 1 })
    .first()
    .innerText();

  expect(
    firstHeading,
    "two different orgs must not render the same organization header",
  ).not.toBe(secondHeading);
});
