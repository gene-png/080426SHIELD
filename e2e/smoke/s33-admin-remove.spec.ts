import { expect, test } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  signIn,
  uniqueEmail,
} from "../helpers/auth";
import { API_BASE } from "../helpers/ids";

/**
 * Issue 3: the admin console had no way to remove a client or a user — only an
 * approved email domain and a service could be removed. Management now offers:
 *
 *   * Archive client   — soft removal; the tenant leaves the live list and the
 *                        intake-queue org index, but its data is retained and
 *                        the action is reversible.
 *   * Deactivate user  — flips User.is_active; sign-in then refuses the
 *                        account, and the row (and everything it authored)
 *                        survives.
 *
 * Every entity here is timestamped-unique: the suite shares a seeded DB, so the
 * spec must not depend on list order or on being the only tenant present.
 */

// These two tests each drive a long multi-page flow (create tenant → approve
// domain → register → deactivate → attempt sign-in → reactivate → sign in), and
// next-dev compiles several routes cold along the way. The default 90s budget
// is not enough for the round trip.
test.describe.configure({ timeout: 240_000 });

async function settleForHydration(
  page: import("@playwright/test").Page,
): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1200);
}

test("management: archiving a client removes it from the list and the org index", async ({
  page,
}) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const legalName = `QA Archive ${stamp} Ltd`;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/management");
  await settleForHydration(page);

  // Create a throwaway tenant to archive.
  await page.getByLabel("New client legal name").fill(legalName);
  await page.getByRole("button", { name: "Create client" }).click();
  await expect(page.getByRole("heading", { name: legalName })).toBeVisible({
    timeout: 30_000,
  });

  // It shows up in the intake-queue org index while active.
  await page.goto("/admin/queue");
  await expect(page.getByText(legalName, { exact: true })).toBeVisible({
    timeout: 30_000,
  });

  // Archive it — behind an explicit confirm, not a single click.
  await page.goto("/admin/management");
  await settleForHydration(page);
  await page.getByRole("button", { name: `Archive ${legalName}` }).click();
  await page.getByRole("button", { name: "Yes, archive" }).click();

  // Gone from the management list...
  await expect(page.getByRole("heading", { name: legalName })).toHaveCount(0, {
    timeout: 30_000,
  });

  // ...and gone from the org index.
  await page.goto("/admin/queue");
  await settleForHydration(page);
  await expect(page.getByText(legalName, { exact: true })).toHaveCount(0);
});

test("management: deactivating a user blocks their sign-in, reactivating restores it", async ({
  page,
  browser,
}) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const legalName = `QA Users ${stamp} Ltd`;
  const domain = `qa${stamp}.example`;
  const userEmail = uniqueEmail(domain);
  const password = "correct horse battery staple!";

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/management");
  await settleForHydration(page);

  await page.getByLabel("New client legal name").fill(legalName);
  await page.getByRole("button", { name: "Create client" }).click();
  await expect(page.getByRole("heading", { name: legalName })).toBeVisible({
    timeout: 30_000,
  });

  // Scope every interaction to THIS client's card. The page lists every tenant,
  // so an unscoped `.first()` would drive a different client's controls.
  const cardFor = (name: string) =>
    page.locator("li", { has: page.getByRole("heading", { name }) }).first();

  // Approve the domain so the user can self-register into this tenant.
  const card0 = cardFor(legalName);
  await card0.getByLabel(`New domain for ${legalName}`).fill(domain);
  await card0.getByRole("button", { name: "Add domain" }).click();
  await expect(card0.getByText(domain, { exact: true })).toBeVisible({
    timeout: 30_000,
  });

  // Create the user through the API, not the sign-up UI: this spec is about
  // deactivation, and the register() helper deliberately returns on either
  // success OR an inline error, so a silently-failed sign-up would surface here
  // as a confusing "user missing from the list" failure instead of its real
  // cause. Asserting the 201 makes the precondition explicit.
  const reg = await page.request.post(`${API_BASE}/auth/register`, {
    data: {
      email: userEmail,
      password,
      display_name: `QA User ${stamp}`,
    },
  });
  expect(
    reg.status(),
    `precondition: registering ${userEmail} must succeed — ${await reg.text()}`,
  ).toBe(201);
  const registered = (await reg.json()) as {
    user: { client_id: string | null };
  };
  expect(
    registered.user.client_id,
    "the approved domain must bind the new user to this tenant",
  ).not.toBeNull();

  // The user now appears in Management, active.
  await page.goto("/admin/management");
  await settleForHydration(page);
  const card = cardFor(legalName);
  await expect(card.getByText(userEmail, { exact: false })).toBeVisible({
    timeout: 30_000,
  });

  // Deactivate. Two steps since UX finding 20: the first click asks for
  // confirmation, naming the user and stating that they are signed out
  // immediately and can be reactivated.
  const userRow = card.locator("li", { hasText: userEmail }).first();
  await userRow
    .getByRole("button", { name: "Deactivate", exact: true })
    .click();
  // Assert the confirm control rather than building a RegExp from the email —
  // the address contains "+", which is a regex quantifier.
  await expect(
    userRow.getByRole("button", { name: "Yes, deactivate" }),
  ).toBeVisible();
  await userRow.getByRole("button", { name: "Yes, deactivate" }).click();
  await expect(userRow.getByText("Deactivated")).toBeVisible({
    timeout: 30_000,
  });

  // Sign-in is now refused with the typed message, not a generic failure.
  const blockedCtx = await browser.newContext();
  const blockedPage = await blockedCtx.newPage();
  await blockedPage.goto("/sign-in");
  await blockedPage.getByLabel("Email").fill(userEmail);
  await blockedPage.getByLabel("Password").fill(password);
  await blockedPage.getByRole("button", { name: "Sign in" }).click();
  await expect(blockedPage.getByText(/deactivated/i).first()).toBeVisible({
    timeout: 30_000,
  });
  expect(new URL(blockedPage.url()).pathname).toContain("/sign-in");
  await blockedCtx.close();

  // Reactivate — the removal is reversible.
  await page.goto("/admin/management");
  await settleForHydration(page);
  const userRow2 = cardFor(legalName)
    .locator("li", { hasText: userEmail })
    .first();
  await userRow2.getByRole("button", { name: "Reactivate" }).click();
  await expect(
    userRow2.getByRole("button", { name: "Deactivate", exact: true }),
  ).toBeVisible({
    timeout: 30_000,
  });

  const okCtx = await browser.newContext();
  const okPage = await okCtx.newPage();
  await signIn(okPage, userEmail, password);
  expect(new URL(okPage.url()).pathname).not.toContain("/sign-in");
  await okCtx.close();
});
