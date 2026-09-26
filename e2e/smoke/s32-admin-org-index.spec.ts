import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

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
  request,
}) => {
  // The spec MINTS its second tenant rather than skipping without one. It used
  // to `test.skip(count < 2, ...)`, and the seed makes one tenant: serially,
  // specs that ran earlier had minted others, but under sharding it ran on a
  // fresh seed and skipped, and the partition check counted the skip as run
  // (#680 round 1). CLAUDE.md: seed the precondition, don't branch on it.
  const token = await adminApiToken(request);
  const legalName = `Queue Scope QA ${Date.now()}`;
  const tenant = await request.post(`${API_BASE}/admin/clients`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { legal_name: legalName },
  });
  expect(tenant.ok(), `create tenant (${tenant.status()})`).toBeTruthy();
  const mintedId = ((await tenant.json()) as { id: string }).id;
  const atlasId = await atlasClientIdViaApi(request, token);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/queue");

  // Both organizations are in the index: the precondition is an assertion.
  await expect(
    page.locator(`a[href="/admin/queue/${mintedId}"]`),
  ).toBeVisible();
  await expect(page.locator(`a[href="/admin/queue/${atlasId}"]`)).toBeVisible();

  // The page H1 is the organization's legal name once one exists. The old
  // advisory-client behaviour rendered the same organization on every page.
  await page.goto(`/admin/queue/${mintedId}`);
  await expect(
    page.getByRole("heading", { name: /^Service requests \(/ }),
  ).toBeVisible();
  const mintedHeading = page.getByRole("heading", { level: 1 }).first();
  await expect(mintedHeading).toHaveText(legalName);

  await page.goto(`/admin/queue/${atlasId}`);
  await expect(
    page.getByRole("heading", { name: /^Service requests \(/ }),
  ).toBeVisible();
  const atlasHeading = await page
    .getByRole("heading", { level: 1 })
    .first()
    .textContent();

  expect(
    atlasHeading,
    "two different orgs must not render the same organization header",
  ).not.toBe(legalName);
});

/**
 * IA appendix: "Filters by client, service, status, and age."
 *
 * The predicates are unit-tested in `lib/admin/filters.test.ts`; this proves the
 * wiring — that typing in the box actually narrows the rendered list, and that
 * filtering to nothing says so instead of looking like an empty queue.
 */
test("admin queue: the organization filter narrows the list and explains an empty result", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/queue");

  const orgLinks = page.locator('a[href^="/admin/queue/"]');
  await expect(orgLinks.first()).toBeVisible({ timeout: 30_000 });
  const total = await orgLinks.count();

  // Filter to a string no organization can contain.
  const filter = page.getByPlaceholder("Filter by organization name…");
  await filter.fill("zzz-no-such-organization-zzz");
  await expect(orgLinks).toHaveCount(0);

  // An empty FILTERED list must not read as an empty queue.
  await expect(
    page.getByText("No organizations match these filters"),
    "a filtered-to-nothing list must say the filters did it",
  ).toBeVisible();

  // Clearing restores every row.
  await filter.fill("");
  await expect(orgLinks).toHaveCount(total);
});
