import { expect, test, type Page } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  CLIENT_EMAIL,
  CLIENT_PASSWORD,
  signIn,
} from "../helpers/auth";
import { resolveBaseUrl } from "../helpers/baseUrl";
import { atlasClientId, atlasServiceId } from "../helpers/ids";

/**
 * SMOKE_TEST.md section 9 (T8): the per-assessment message thread + admin inbox.
 *
 * A message posted by the client on their assessment thread must reach the
 * SHIELD analyst in two places — the service's admin workspace thread AND the
 * /admin/messages inbox, where it shows an unread badge. The analyst's reply
 * flows back to the client, and opening the thread clears the unread count
 * (apps/api/app/routes/messages.py: a GET marks the counterparty's messages
 * read).
 *
 * Two tenants of the same browser are involved, so the test runs a client
 * context and an admin context side by side. It works the SEEDED Atlas CSF
 * service: the client reaches its thread via /self-assessment/<id>?type=nist_csf
 * (the page renders a MessageThread for any known assessment type), and the
 * admin reaches the same thread through the CSF workspace (which renders a
 * MessageThread once an assessment exists — we mint one if the seed lacks it).
 *
 * Assertions key off the unique message bodies (never the shared, duplicated
 * service title) so the shared, mutating seed DB can't confuse the rows.
 */

const BASE_URL = resolveBaseUrl();

const UNREAD_BADGE = /^\d+ new$/;

/**
 * Guarantee the admin CSF workspace can render its MessageThread: the thread is
 * gated behind an assessment existing for the service. If the seed left none,
 * mint a fresh draft and reload.
 */
async function ensureCsfAssessment(
  page: Page,
  csfServiceId: string,
): Promise<void> {
  const latest = await page.request.get(
    `/api/proxy/csf/services/${csfServiceId}/assessments/latest`,
  );
  if (!latest.ok()) {
    const created = await page.request.post(
      `/api/proxy/csf/services/${csfServiceId}/assessments`,
    );
    expect(created.ok()).toBeTruthy();
    await page.reload();
  }
}

test("client message reaches the admin inbox + workspace, reply returns, and opening clears unread", async ({
  browser,
}) => {
  // Two contexts + sign-ins + a workspace open on a shared next-dev server:
  // triple the per-step budget.
  test.slow();

  const stamp = `${Date.now()}${Math.floor(Math.random() * 1000)}`;
  const CLIENT_MSG = `CLIENT-QUESTION-${stamp}`;
  const ADMIN_MSG = `ANALYST-REPLY-${stamp}`;

  const clientCtx = await browser.newContext({ baseURL: BASE_URL });
  const adminCtx = await browser.newContext({ baseURL: BASE_URL });
  const clientPage = await clientCtx.newPage();
  const adminPage = await adminCtx.newPage();

  try {
    // Resolve the seeded Atlas ids up front via the admin proxy: nist_csf is one
    // of the self-assessment page's known types (so the client can open its
    // thread) and the CSF admin workspace renders the same thread. Signing the
    // analyst in first is harmless — unread is cleared by OPENING the thread, not
    // by logging in.
    await signIn(adminPage, ADMIN_EMAIL, ADMIN_PASSWORD);
    const csfServiceId = await atlasServiceId(adminPage, "nist_csf");
    const atlasId = await atlasClientId(adminPage);

    // --- Client posts on their assessment thread -------------------------
    await signIn(clientPage, CLIENT_EMAIL, CLIENT_PASSWORD);
    await clientPage.goto(`/self-assessment/${csfServiceId}?type=nist_csf`);
    const clientBox = clientPage.getByRole("textbox", {
      name: "Write a message",
    });
    await expect(clientBox).toBeVisible({ timeout: 30000 });
    await clientBox.fill(CLIENT_MSG);
    const clientPosted = clientPage.waitForResponse(
      (r) =>
        r.url().includes(`/services/${csfServiceId}/messages`) &&
        r.request().method() === "POST" &&
        r.ok(),
      { timeout: 60000 },
    );
    await clientPage.getByRole("button", { name: "Send", exact: true }).click();
    await clientPosted;
    await expect(clientPage.getByText(CLIENT_MSG)).toBeVisible({
      timeout: 15000,
    });

    // --- Admin sees an unread badge in the /admin/messages inbox ---------
    const switched = await adminPage.request.post("/api/active-client", {
      data: { clientId: atlasId },
    });
    expect(switched.ok()).toBeTruthy();

    await adminPage.goto("/admin/messages");
    // The inbox row is a link whose preview carries the client's message.
    const inboxRow = adminPage.locator("a", { hasText: CLIENT_MSG });
    await expect(inboxRow).toBeVisible({ timeout: 30000 });
    // ...and it wears an unread badge because the analyst hasn't opened it.
    await expect(inboxRow.getByText(UNREAD_BADGE)).toBeVisible({
      timeout: 15000,
    });

    // --- Admin opens the thread (clears unread) and replies --------------
    await inboxRow.click();
    await adminPage.waitForURL(
      new RegExp(`/admin/services/${csfServiceId}/csf`),
      { timeout: 30000 },
    );
    await ensureCsfAssessment(adminPage, csfServiceId);

    // The client's message is present in the admin workspace thread.
    await expect(adminPage.getByText(CLIENT_MSG)).toBeVisible({
      timeout: 30000,
    });

    const adminBox = adminPage.getByRole("textbox", {
      name: "Write a message",
    });
    await expect(adminBox).toBeVisible({ timeout: 15000 });
    await adminBox.fill(ADMIN_MSG);
    const adminPosted = adminPage.waitForResponse(
      (r) =>
        r.url().includes(`/services/${csfServiceId}/messages`) &&
        r.request().method() === "POST" &&
        r.ok(),
      { timeout: 60000 },
    );
    await adminPage.getByRole("button", { name: "Send", exact: true }).click();
    await adminPosted;
    await expect(adminPage.getByText(ADMIN_MSG)).toBeVisible({
      timeout: 15000,
    });

    // --- Opening the thread cleared the unread count ---------------------
    // Reopen the inbox (fresh fetch). The row's preview is now the analyst's
    // reply, and because the GET above marked the client's message read, the
    // row no longer shows an unread badge.
    await adminPage.goto("/admin/messages");
    const clearedRow = adminPage.locator("a", { hasText: ADMIN_MSG });
    await expect(clearedRow).toBeVisible({ timeout: 30000 });
    await expect(clearedRow.getByText(UNREAD_BADGE)).toHaveCount(0);

    // --- Client sees the analyst's reply ---------------------------------
    await clientPage.goto(`/self-assessment/${csfServiceId}?type=nist_csf`);
    await expect(clientPage.getByText(ADMIN_MSG)).toBeVisible({
      timeout: 30000,
    });
  } finally {
    await clientCtx.close();
    await adminCtx.close();
  }
});
