import { expect, test } from "@playwright/test";

/**
 * SMOKE_TEST.md defect 5: an unknown URL must render the custom app-consistent
 * not-found page (nav shell + onward recovery links), not the bare Next.js
 * default 404 dead-end.
 */

test("unknown route renders custom not-found with onward links", async ({
  page,
}) => {
  const res = await page.goto("/definitely-not-a-page");
  // Next.js serves not-found.tsx with a 404 status.
  expect(res?.status()).toBe(404);

  // Custom copy, not the bare Next default ("This page could not be found").
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible();

  // The app shell (public header brand mark) is present.
  await expect(
    page.getByRole("link", { name: /SHIELD/ }).first(),
  ).toBeVisible();

  // At least one onward recovery link is present and points somewhere real.
  const recovery = page.getByRole("navigation", { name: "Recovery links" });
  await expect(recovery.getByRole("link", { name: "Home" })).toBeVisible();
  await expect(
    recovery.getByRole("link", { name: "My Assessments" }),
  ).toBeVisible();
  await expect(recovery.getByRole("link", { name: "Sign in" })).toBeVisible();

  // Home link navigates back to the marketing home (not a dead end).
  await recovery.getByRole("link", { name: "Home" }).click();
  await expect(page).toHaveURL(/\/$/);
});
