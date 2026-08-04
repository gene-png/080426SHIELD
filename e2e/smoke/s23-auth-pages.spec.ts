import { expect, test, type Page } from "@playwright/test";

import { signIn, uniqueEmail } from "../helpers/auth";
import { extractToken, fetchLatestMessage } from "../helpers/mailhog";

/**
 * Sprint 8 T3 (SMOKE §25 web-page eyeball -> spec-backed): browser-drives the
 * three auth PAGES the API-path proof (s21-email-verify.spec.ts) never touched —
 * /verify-email, /forgot-password, /reset-password. s21 stays as the API-path
 * proof; this spec proves the pages render and complete their flows in the
 * browser, then that a reset password actually signs in.
 *
 * OPT-IN like s21: email delivery is off on a stock stack, so with no message in
 * MailHog these tests SKIP rather than fail. The dev/CI compose ships delivery
 * ON (Sprint 7 T3), so both tests execute the real token flow through the wire.
 *
 * Registration is driven via the same proxy the UI uses (a precondition, not one
 * of the pages under proof); the token is read out of MailHog with the T0
 * helper, subject-matched so registration's own verification mail never wins the
 * race over the reset mail.
 */

const PASSWORD = "correct horse battery staple!";
const NEW_PASSWORD = "fresh reset battery staple 77!";

/**
 * Give the App Router client bundle time to hydrate before submitting a form: an
 * unhydrated submit click triggers a native GET submit that reloads the page and
 * drops React state (and, on /reset-password, the ?token= query). Mirrors the
 * settle in helpers/auth.ts. networkidle plus a short wait is reliable enough in
 * Next dev.
 */
async function settleForHydration(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(1500);
}

test("verify-email page confirms the address from the emailed token", async ({
  page,
  request,
}) => {
  const email = uniqueEmail("atlas.example");
  const reg = await request.post("/api/proxy/auth/register", {
    data: { email, password: PASSWORD, display_name: "Page Verify" },
  });
  expect(reg.status(), await reg.text()).toBe(201);

  const message = await fetchLatestMessage(request, email, {
    subject: "confirm",
  });
  test.skip(
    message === null,
    "email delivery disabled (set SHIELD_EMAIL_DELIVERY_ENABLED=true to run)",
  );

  const token = extractToken(message!.Content.Body);
  expect(token, "verification token in email body").not.toBeNull();

  // Drive the PAGE: VerifyEmailClient POSTs the token on mount and renders the
  // outcome. The success panel is a role=status with the confirmation copy.
  await page.goto(`/verify-email?token=${token}`);
  await expect(page.getByText("Your email address is confirmed.")).toBeVisible({
    timeout: 20000,
  });
});

test("forgot + reset pages set a new password that signs in", async ({
  page,
  request,
}) => {
  const email = uniqueEmail("atlas.example");
  const reg = await request.post("/api/proxy/auth/register", {
    data: { email, password: PASSWORD, display_name: "Page Reset" },
  });
  expect(reg.status(), await reg.text()).toBe(201);

  // Request the reset by driving /forgot-password in the browser.
  await page.goto("/forgot-password");
  await settleForHydration(page);
  await page.locator("#email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  // Enumeration-safe uniform confirmation (_UNIFORM_EMAIL_ACTION_MSG).
  await expect(page.getByText(/sent a message with next steps/i)).toBeVisible({
    timeout: 15000,
  });

  // Registration also emails the recipient, so subject-match the reset mail
  // rather than "latest for recipient".
  const message = await fetchLatestMessage(request, email, {
    subject: "reset",
  });
  test.skip(
    message === null,
    "email delivery disabled (set SHIELD_EMAIL_DELIVERY_ENABLED=true to run)",
  );

  const token = extractToken(message!.Content.Body);
  expect(token, "reset token in email body").not.toBeNull();

  // Complete the reset by driving /reset-password in the browser. Settle before
  // the single submit: a native submit here would drop the ?token= query.
  await page.goto(`/reset-password?token=${token}`);
  await settleForHydration(page);
  await expect(page.locator("#password")).toBeVisible({ timeout: 15000 });
  await page.locator("#password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await expect(page.getByText("Your password has been reset.")).toBeVisible({
    timeout: 20000,
  });

  // The new password actually signs in — proves the reset took effect end-to-end.
  await signIn(page, email, NEW_PASSWORD);
});
