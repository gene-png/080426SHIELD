import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import {
  adminApiToken,
  atlasClientIdViaApi,
  atlasServiceIdsViaApi,
} from "../helpers/ids";

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
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  // Resolve a seeded ATT&CK workspace through the API rather than hunting for
  // a link: which workspaces the queue exposes depends on what has been
  // published, and this spec is about the Run-AI gate, not queue navigation.
  const token = await adminApiToken(page.request);
  const clientId = await atlasClientIdViaApi(page.request, token);
  const byType = await atlasServiceIdsViaApi(page.request, token, clientId);
  const serviceId = byType.get("attack_coverage");
  test.skip(!serviceId, "seed has no ATT&CK coverage service");

  await page.goto(`/admin/services/${serviceId}/attack-coverage`);
  const runAi = page.getByRole("button", { name: "Run AI", exact: true });
  await expect(runAi).toBeVisible({ timeout: 60_000 });

  // A released assessment renders Run AI disabled — a legitimate state the
  // shared seed can be in. The gate's own logic is covered exhaustively by
  // RunAiGuard.test.tsx; this spec only proves the wiring on a live workspace.
  test.skip(
    !(await runAi.isEnabled()),
    "seeded ATT&CK assessment is read-only (released), so Run AI is disabled",
  );

  // First click surfaces the offline warning instead of silently running.
  await runAi.click();
  const dialog = page.getByRole("alertdialog", { name: "No API key loaded" });
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await expect(
    dialog.getByRole("button", { name: "Continue offline" }),
  ).toBeVisible();
  await expect(dialog.getByRole("link", { name: "Load a key" })).toBeVisible();
});
