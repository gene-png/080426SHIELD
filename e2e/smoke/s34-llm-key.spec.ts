import { expect, test, type APIRequestContext } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";

/**
 * Issue 2: an admin must be TOLD when AI will produce offline output, and be
 * able to fix it without a redeploy.
 *
 * Before this, the only key path was an environment variable read once at
 * boot, and the only warning lived on one of five workspaces — so an admin
 * could work a whole session believing "Run AI" analysed their client's data
 * when every result was canned fixture content.
 *
 * The stack under test runs in fixture mode with no key, which is exactly the
 * state these assertions describe. The spec deliberately does NOT paste a real
 * key: validating one would require egressing to the provider from CI.
 */

test.describe.configure({ timeout: 180_000 });

/**
 * A throwaway tenant with an ATT&CK service and a DRAFT coverage assessment.
 *
 * Its own tenant rather than Atlas, for two reasons. It keeps the shared seed
 * untouched — and an unreleased ATT&CK service in Atlas would surface on the
 * client's /home as an "In progress" card linking to /assessments, which `s31`
 * asserts against (it expects "In progress" to mean a resumable
 * self-assessment). Isolation avoids borrowing that problem.
 */
async function createAttackWorkspace(
  request: APIRequestContext,
  token: string,
): Promise<{ clientId: string; serviceId: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const stamp = Date.now();

  const tenant = await request.post(`${API_BASE}/admin/clients`, {
    headers: auth,
    data: { legal_name: `Run-AI Guard QA ${stamp}` },
  });
  expect(tenant.ok(), `create tenant (${tenant.status()})`).toBeTruthy();
  const clientId = ((await tenant.json()) as { id: string }).id;

  const headers = { ...auth, "X-Client-Id": clientId };
  const svc = await request.post(`${API_BASE}/attack/services`, {
    headers,
    data: { kind: "attack_coverage", title: `Run-AI Guard QA ${stamp}` },
  });
  expect(svc.status(), `open ATT&CK service (${await svc.text()})`).toBe(201);
  const serviceId = ((await svc.json()) as { id: string }).id;

  // Pre-seeds an unscored row per technique and lands in DRAFT — the state
  // that keeps Run AI enabled.
  const assessment = await request.post(
    `${API_BASE}/attack/services/${serviceId}/assessments`,
    { headers },
  );
  expect(
    assessment.status(),
    `create assessment (${await assessment.text()})`,
  ).toBe(201);
  expect(
    ((await assessment.json()) as { status: string }).status.toLowerCase(),
  ).toBe("draft");

  return { clientId, serviceId };
}

test("admin: the offline warning appears on every admin page and offers the fix", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  // The banner is shell-level, so it shows on the landing page and elsewhere —
  // not only on the one workspace that used to carry it.
  for (const path of ["/admin/queue", "/admin/management", "/admin/audit"]) {
    await page.goto(path);
    const banner = page.getByText("AI is not live.", { exact: false }).first();
    await expect(banner, `${path} must warn that AI is offline`).toBeVisible({
      timeout: 30_000,
    });
  }

  // And it links to where the key is entered — never a dead end.
  await page.goto("/admin/queue");
  const fixLink = page.getByRole("link", { name: "Load an API key" }).first();
  await expect(fixLink).toBeVisible({ timeout: 30_000 });
  await fixLink.click();
  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: 30_000 })
    .toBe("/admin/management");
});

test("admin: the key panel reports offline state and refuses a bad key without saving it", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/management");

  await expect(
    page.getByRole("heading", { name: "AI provider key" }),
  ).toBeVisible({ timeout: 30_000 });

  // Current state is surfaced plainly: offline, and no key loaded. The page
  // carries exactly one key panel, so these don't need scoping — and scoping
  // by "the div containing the heading" would land on the card header, which
  // holds the title but none of the status text.
  await expect(page.getByText("Offline", { exact: true })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("key: not loaded")).toBeVisible();

  // The input exists and is masked — the key must not be shoulder-surfable.
  const input = page.getByLabel("Provider API key");
  await expect(input).toHaveAttribute("type", "password");

  // A bogus key is rejected by the provider and NOT stored: the panel still
  // reports no key afterwards. (Fixture-mode stacks have no live provider, so
  // the failure arrives as a validation refusal either way — the contract
  // being pinned is "rejected keys change nothing".)
  await input.fill("sk-ant-obviously-not-a-real-key");
  await page.getByRole("button", { name: /Save key|Replace key/ }).click();
  await expect(page.getByRole("alert").first()).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("key: not loaded")).toBeVisible();
});

test("admin: Run AI warns before producing offline output, then proceeds once acknowledged", async ({
  page,
  request,
}) => {
  test.slow();

  // Seed a workspace whose Run AI button CANNOT be disabled.
  //
  // This test used to resolve the seeded Atlas ATT&CK service and then
  // self-skip twice: once if the seed had no such service, and once if its
  // assessment was already released (which renders Run AI read-only). Whether
  // the browser ever exercised the guard therefore depended on shared database
  // state nobody controls — and a spec that skips is UNTESTED, not passing.
  // That skip is exactly what hid the fail-open race below until the first
  // full-suite run.
  //
  // A fresh tenant with a fresh DRAFT assessment makes `readOnly`
  // (approved || released) impossible, so the assertions always run.
  const token = await adminApiToken(request);
  const { serviceId } = await createAttackWorkspace(request, token);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${serviceId}/attack-coverage`);
  const runAi = page.getByRole("button", { name: "Run AI", exact: true });
  await expect(runAi).toBeVisible({ timeout: 60_000 });

  // Asserted, not skipped on: a draft assessment must leave Run AI actionable.
  // If this ever fails, the guard genuinely cannot be reached and the rest of
  // the test would have been silently skipped under the old shape.
  await expect(
    runAi,
    "a freshly drafted assessment must leave Run AI enabled",
  ).toBeEnabled();

  // First click surfaces the offline warning instead of silently running.
  //
  // Deliberately NOT preceded by a wait on the ai-status response: clicking
  // while that request is still in flight is precisely what broke the guard
  // (it failed open on a null status and ran, writing 1646 fields of canned
  // output with no warning — caught by the first full-suite run of this spec,
  // which standalone had always skipped). Keep the click eager so this stays a
  // regression test for that race, not just for the happy path.
  await runAi.click();
  const dialog = page.getByRole("alertdialog", { name: "No API key loaded" });
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(
    dialog.getByRole("button", { name: "Continue offline" }),
  ).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Load a key" })).toBeVisible();
});
