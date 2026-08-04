import { expect, test } from "@playwright/test";

import { register, uniqueEmail } from "../helpers/auth";

/**
 * Two sign-up cases:
 *  1. Open self-registration (D-034): a brand-new user with a never-before-seen
 *     company domain self-registers with no admin involvement and lands signed
 *     in on /intake (the tenant is auto-provisioned).
 *  2. Friendly field-scoped error copy (SMOKE_TEST.md defect 4 / D-016): a
 *     duplicate email surfaces friendly copy on the email field, never the raw
 *     upstream "Request validation failed." string.
 */

const PASSWORD = "correct horse battery staple!";

test("duplicate-email registration shows friendly copy on the email field", async ({
  page,
  request,
}) => {
  const email = uniqueEmail("atlas.example");

  // Pre-create the account through the same proxy the form uses, so the UI
  // attempt below is a guaranteed duplicate regardless of run order.
  const seeded = await request.post("/api/proxy/auth/register", {
    data: { email, password: PASSWORD, display_name: "Dupe First" },
  });
  expect(seeded.status(), await seeded.text()).toBe(201);

  // Now attempt the same email through the sign-up UI (fresh, unauthenticated).
  await register(page, "Dupe Second", email, PASSWORD);

  await expect(
    page.getByText(
      "An account already exists for that email. Sign in instead.",
    ),
  ).toBeVisible();
  // The raw upstream validation string must never reach the user.
  await expect(page.getByText(/request validation failed/i)).toHaveCount(0);
  // The failed attempt stays on the sign-up page (no navigation to /intake).
  expect(new URL(page.url()).pathname).toContain("/sign-up");
});

test("a brand-new user self-registers and lands signed in on /intake", async ({
  page,
}) => {
  // A syntactically valid, never-before-seen company domain. With open
  // self-registration (D-034) no admin pre-approval is needed: the org is
  // auto-provisioned and the new user is signed straight into /intake.
  const email = uniqueEmail(`newco-${Date.now()}.com`);

  await register(page, "Self Serve", email, PASSWORD);

  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: 20000 })
    .toContain("/intake");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
    timeout: 20000,
  });
});
