import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * SMOKE_TEST.md section 2 (B2): the /admin/management UI ITSELF.
 *
 * Closes the coverage gap called out in §2: prior coverage exercised only the
 * admin API the page calls (in s13 setup). This spec drives the rendered
 * Management page — create a client, approve a domain, see both reflected in
 * the list, remove the domain, see the removal reflected — so the wiring
 * between the form controls, the API, and the re-rendered list is proven
 * end-to-end.
 *
 * The suite shares a seeded DB across runs, so every entity name here is
 * timestamped-unique to survive accumulation (no reliance on list order or on
 * being the only client present).
 *
 * T9 (D-018): a reserved/special-use TLD (.test/.invalid/.localhost) is
 * rejected at approval with a typed 422 whose friendly copy surfaces in the
 * card; a `.example` domain (accepted by the email validator) still approves.
 */

/**
 * Let the App Router client bundle hydrate before we drive the controlled
 * inputs — a pre-hydration submit reloads the page and drops typed values
 * (same race the auth helper guards). networkidle + a short settle is enough
 * in Next.js dev mode.
 */
async function settleForHydration(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1200);
}

test("management UI: create client, approve + remove a domain, list reflects each change", async ({
  page,
}) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const legalName = `QA Mgmt ${stamp} Ltd`;
  // `.example` is a reserved-for-documentation TLD the email validator ACCEPTS
  // (unlike .test/.invalid/.localhost), so an approved domain here is one a
  // user could actually register against.
  const domain = `qa-mgmt-${stamp}.example`;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/management");
  await expect(
    page.getByRole("heading", { name: "Management", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await settleForHydration(page);

  // --- Create a client via the form (NOT the API) ---------------------------
  const nameInput = page.getByLabel("New client legal name");
  const createBtn = page.getByRole("button", { name: /^Creat(e|ing)/ });
  // Our client's list card, scoped by its unique legal name (many QA-* junk
  // clients accumulate in the shared DB, so never rely on being the only one).
  const clientCard = page.getByRole("listitem").filter({ hasText: legalName });

  await expect(async () => {
    await nameInput.fill(legalName);
    await expect(createBtn).toBeEnabled();
    await createBtn.click();
    // The list re-renders (reload()) with our new client card.
    await expect(clientCard).toBeVisible({ timeout: 10000 });
  }).toPass({ timeout: 45000 });

  const domainInput = clientCard.getByLabel(`New domain for ${legalName}`);
  const addBtn = clientCard.getByRole("button", { name: "Add domain" });

  // --- T9: a reserved/special-use TLD is rejected with friendly copy --------
  // `.test` passes the format check but the email validator 422s it, so no user
  // could ever register on it. The route rejects it (reason=domain_reserved_tld,
  // D-018) and the Management UI surfaces the typed message — never a chip.
  const reservedDomain = `qa-mgmt-${stamp}.test`;
  await expect(async () => {
    await domainInput.fill(reservedDomain);
    await expect(addBtn).toBeEnabled();
    await addBtn.click();
    await expect(
      clientCard.getByText(/reserved or special-use domain/i),
    ).toBeVisible({ timeout: 10000 });
  }).toPass({ timeout: 30000 });
  // The rejected domain never becomes an approved chip.
  await expect(
    clientCard.getByText(reservedDomain, { exact: true }),
  ).toHaveCount(0);

  // --- Approve (add) a valid domain, scoped to our client's card ------------
  await expect(async () => {
    await domainInput.fill(domain);
    await expect(addBtn).toBeEnabled();
    await addBtn.click();
    // The chip for the approved domain appears in this client's card.
    await expect(clientCard.getByText(domain, { exact: true })).toBeVisible({
      timeout: 10000,
    });
  }).toPass({ timeout: 30000 });

  // The "None yet" empty-state copy is gone now that a domain is approved.
  await expect(clientCard.getByText("None yet", { exact: false })).toHaveCount(
    0,
  );

  // --- Remove the domain, list reflects the removal -------------------------
  const removeBtn = clientCard.getByRole("button", {
    name: `Remove ${domain}`,
  });
  await expect(removeBtn).toBeVisible();
  await removeBtn.click();

  // Removal is reflected: the chip is gone from the re-rendered list.
  await expect(clientCard.getByText(domain, { exact: true })).toHaveCount(0, {
    timeout: 10000,
  });
});
