import { expect, test } from "@playwright/test";

import { uniqueEmail } from "../helpers/auth";
import {
  extractToken,
  fetchLatestMessage,
  subjectOf,
} from "../helpers/mailhog";

/**
 * Sprint 6 T5 (D-028): email verification + password reset via MailHog.
 *
 * OPT-IN. Email delivery is off by default (SHIELD_EMAIL_DELIVERY_ENABLED=false),
 * so on a stock stack these specs SKIP rather than fail — mirroring the
 * opt-in live-AI specs (T1). To run them, bring the api up with
 * SHIELD_EMAIL_DELIVERY_ENABLED=true (MailHog is already wired on :1025 / :8025)
 * and re-run. When delivery is on, the specs register through the same proxy the
 * UI uses, read the real message out of the MailHog API, extract the token from
 * the link, and complete the verify / reset flow end to end.
 *
 * The MailHog reader (MAILHOG_API, fetchLatestMessage, extractToken) moved to
 * e2e/helpers/mailhog.ts in Sprint 8 T0; this spec is unchanged behaviorally.
 */

const PASSWORD = "correct horse battery staple!";
const NEW_PASSWORD = "brand new battery staple 99!";

test("verification email confirms the address (MailHog)", async ({
  request,
}) => {
  const email = uniqueEmail("atlas.example");
  const reg = await request.post("/api/proxy/auth/register", {
    data: { email, password: PASSWORD, display_name: "Verify Me" },
  });
  expect(reg.status(), await reg.text()).toBe(201);

  const message = await fetchLatestMessage(request, email);
  test.skip(
    message === null,
    "email delivery disabled (set SHIELD_EMAIL_DELIVERY_ENABLED=true to run)",
  );

  const token = extractToken(message!.Content.Body);
  expect(token, "verification token in email body").not.toBeNull();

  const verify = await request.post("/api/proxy/auth/verify-email", {
    data: { token },
  });
  expect(verify.status(), await verify.text()).toBe(200);
  expect((await verify.json()).email_verified).toBe(true);
});

test("forgot-password link resets the password (MailHog)", async ({
  request,
}) => {
  const email = uniqueEmail("atlas.example");
  const reg = await request.post("/api/proxy/auth/register", {
    data: { email, password: PASSWORD, display_name: "Reset Me" },
  });
  expect(reg.status(), await reg.text()).toBe(201);

  // Drain the verification email so the reset email is the latest one.
  await fetchLatestMessage(request, email);

  const forgot = await request.post("/api/proxy/auth/forgot-password", {
    data: { email },
  });
  expect(forgot.status()).toBe(200);

  const message = await fetchLatestMessage(request, email);
  test.skip(
    message === null,
    "email delivery disabled (set SHIELD_EMAIL_DELIVERY_ENABLED=true to run)",
  );

  // The latest message must be the reset (subject), not the earlier verify.
  expect(subjectOf(message!).toLowerCase()).toContain("reset");
  const token = extractToken(message!.Content.Body);
  expect(token).not.toBeNull();

  const reset = await request.post("/api/proxy/auth/reset-password", {
    data: { token, password: NEW_PASSWORD },
  });
  expect(reset.status(), await reset.text()).toBe(200);
});
