import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import {
  adminApiToken,
  API_BASE,
  atlasClientIdViaApi,
  atlasServiceIdsViaApi,
} from "../helpers/ids";

/**
 * T6, the client-scoped navigation frame (#736 issuecomment-6204357376):
 *   1. a client's frame: overview -> rail -> a service's section, with the
 *      section bar's links each on their own URL;
 *   2. an old `/admin/services/{id}/{segment}` URL lands on the new one;
 *   3. the URL is not authorization: another client's service, named under
 *      Atlas's path, is not found, and its workspace never opens.
 * The other workspace specs still open the OLD URLs on purpose, so they cover
 * the redirect on every run; this spec covers the new URLs directly.
 */

const LOAD_MS = 30_000;

test("a client's frame: overview, rail, and sections with their own URLs", async ({
  page,
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const atlas = await atlasClientIdViaApi(request, token);
  const ids = await atlasServiceIdsViaApi(request, token, atlas);
  const csfId = ids.get("nist_csf");
  expect(csfId, "seeded Atlas CSF service").toBeTruthy();

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/clients/${atlas}`);
  const rail = page.getByRole("navigation", { name: "Client services" });
  await expect(rail).toBeVisible({ timeout: LOAD_MS });
  await expect(rail.getByRole("link", { name: "Risk Register" })).toBeVisible();

  await page.goto(
    `/admin/clients/${atlas}/services/csf/overview?service=${csfId}`,
  );
  const sections = page.getByRole("navigation", { name: "Service sections" });
  await expect(sections).toBeVisible({ timeout: LOAD_MS });
  // CSF folds Inputs into AI draft.
  await expect(sections.getByRole("link", { name: "Inputs" })).toHaveCount(0);
  await sections.getByRole("link", { name: "Review", exact: true }).click();
  await expect
    .poll(() => page.url(), { timeout: LOAD_MS })
    .toContain(`/admin/clients/${atlas}/services/csf/review?service=${csfId}`);
  await expect(
    page
      .getByRole("navigation", { name: "Service sections" })
      .getByRole("link", { name: "Review", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  // CSF is split (#1378): the section shows its own header.
  await expect(
    page.getByRole("heading", { level: 1, name: "Review", exact: true }),
  ).toBeVisible({ timeout: LOAD_MS });
});

test("an old workspace URL lands on the client frame", async ({
  page,
  request,
}) => {
  const token = await adminApiToken(request);
  const atlas = await atlasClientIdViaApi(request, token);
  const ids = await atlasServiceIdsViaApi(request, token, atlas);
  const tdId = ids.get("tech_debt");
  expect(tdId, "seeded Atlas Tech Debt service").toBeTruthy();

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${tdId}/tech-debt`);
  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: LOAD_MS })
    .toBe(`/admin/clients/${atlas}/services/tech-debt/overview`);
  expect(new URL(page.url()).searchParams.get("service")).toBe(tdId);
  await expect(
    page.getByRole("navigation", { name: "Service sections" }),
  ).toBeVisible({ timeout: LOAD_MS });
});

test("another client's service under Atlas's URL is not found", async ({
  page,
  request,
}) => {
  const token = await adminApiToken(request);
  const atlas = await atlasClientIdViaApi(request, token);
  const auth = { Authorization: `Bearer ${token}` };

  // A tenant of our own with one Tech Debt service: never Atlas's.
  const other = await request.post(`${API_BASE}/admin/clients`, {
    headers: auth,
    data: { legal_name: `E2E T6 Other ${Date.now()}` },
  });
  expect(other.ok(), "create the other client").toBeTruthy();
  const otherId = ((await other.json()) as { id: string }).id;
  const svc = await request.post(`${API_BASE}/tech-debt/services`, {
    headers: { ...auth, "X-Client-Id": otherId },
    data: { kind: "tech_debt", title: "E2E T6 other client's service" },
  });
  expect(svc.ok(), "create the other client's service").toBeTruthy();
  const otherSvc = ((await svc.json()) as { id: string }).id;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(
    `/admin/clients/${atlas}/services/tech-debt/overview?service=${otherSvc}`,
  );
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible({ timeout: LOAD_MS });
  await expect(
    page.getByRole("navigation", { name: "Service sections" }),
  ).toHaveCount(0);

  // The same service under its own client's URL opens.
  await page.goto(
    `/admin/clients/${otherId}/services/tech-debt/overview?service=${otherSvc}`,
  );
  await expect(
    page.getByRole("navigation", { name: "Service sections" }),
  ).toBeVisible({ timeout: LOAD_MS });
});
