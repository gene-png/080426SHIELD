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
 *  3. The same guarantee for a SCHEMA refusal (#317). Case 2 takes the
 *     `email_exists` branch, so for months the only assertion in the repo
 *     forbidding that string never ran against the input that produces it.
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

test("a malformed email shows the friendly prompt, not the raw validation string", async ({
  page,
}) => {
  // `noValidate` on the form and a permissive `type="email"` mean the browser
  // lets this through, so the request reaches the API and fails Pydantic's
  // `EmailStr` — a schema 422, which since #307 carries a `schema_*` reason.
  await register(page, "Malformed Email", "abc@x", PASSWORD);

  // The positive state first. Asserting the absence against a page that is
  // still resolving the POST passes whether or not the defect is present.
  await expect(
    page.getByText(/please double-check your name, email/i),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByText(/request validation failed/i)).toHaveCount(0);
  expect(new URL(page.url()).pathname).toContain("/sign-up");
});

test("a too-short password shows the friendly prompt, not the raw validation string", async ({
  page,
}) => {
  // `min_length=12` in `schemas/auth.py`. The interesting half is the FIELD:
  // before the fix this rendered under Email, naming an input that was fine.
  await register(page, "Short Password", uniqueEmail("atlas.example"), "short");

  await expect(
    page.getByText(/please double-check your name, email/i),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByText(/request validation failed/i)).toHaveCount(0);
  expect(new URL(page.url()).pathname).toContain("/sign-up");
});
