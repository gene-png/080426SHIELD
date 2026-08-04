import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * SMOKE_TEST.md section 0 (bring-up): the marketing home renders cleanly and
 * an admin can sign in to an authenticated session.
 */

// Benign next-dev console noise that is not an app defect (the app runs under
// a dev server in this harness). Real errors — hydration failures, CSP blocks,
// unhandled exceptions — are NOT matched by these and still fail the test.
const DEV_NOISE = [
  /failed to load resource: .*404/i, // e.g. favicon/asset 404 under dev
  /download the react devtools/i,
];

test("home renders without console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (
      msg.type() === "error" &&
      !DEV_NOISE.some((re) => re.test(msg.text()))
    ) {
      errors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    errors.push(err.message);
  });

  await page.goto("/");
  await expect(page).toHaveTitle(/SHIELD/i);
  // The public header brand mark is present on the marketing home.
  await expect(
    page.getByRole("link", { name: /SHIELD/ }).first(),
  ).toBeVisible();

  expect(errors, `console errors on home: ${errors.join(" | ")}`).toEqual([]);
});

test("home copy has no stale reviewer role and uses spec ATT&CK name", async ({
  page,
}) => {
  await page.goto("/");
  const body = (await page.locator("body").innerText()).toLowerCase();
  // The reviewer role was collapsed into admin (Work Order A3); no marketing
  // copy should still advertise a reviewer walk.
  expect(body).not.toContain("reviewer");
  // The ATT&CK service uses its spec name, not the old "Attack Surface Mapping".
  await expect(page.getByText("MITRE ATT&CK Coverage Mapping")).toBeVisible();
});

test("admin sign-in lands authenticated (nav shows Sign out)", async ({
  page,
}) => {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  // Admin sees the Admin nav entry once signed in.
  await expect(page.getByRole("link", { name: "Admin" })).toBeVisible();
});
