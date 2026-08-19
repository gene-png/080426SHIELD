import { expect, test } from "@playwright/test";

import { CLIENT_EMAIL, CLIENT_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * After an admin releases a NIST CSF deliverable, the client can open a
 * maturity dashboard: per-function current-vs-target plus prioritized gaps.
 * Setup drives the admin API; the client views through the real UI.
 *
 * CSF was the only assessment service with no client dashboard —
 * `dashboardPathFor` returned null for `nist_csf`, so a client saw a CSF gap
 * count on /home and had no way to open the results.
 */

test("client views a released NIST CSF maturity dashboard", async ({
  page,
  request,
}) => {
  // Scoring 106 subcategories over the API, then a finalize that renders four
  // documents, is well past the default budget on a next-dev server that is
  // also serving the rest of the suite.
  test.slow();

  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/csf/services`, {
      headers: H,
      data: { kind: "nist_csf", title: "E2E CSF Dashboard" },
    })
  ).json();
  const serviceId = svc.id as string;

  const assess = await (
    await request.post(`${API_BASE}/csf/services/${serviceId}/assessments`, {
      headers: H,
    })
  ).json();
  const answers = assess.answers as { id: string }[];
  // Tier 2 against the default target of 3 leaves every subcategory a gap, so
  // the remediation section has something real to render AND the truncation
  // disclosure below is genuinely exercised rather than trivially satisfied.
  for (const ans of answers) {
    await request.patch(`${API_BASE}/csf/answers/${ans.id}`, {
      headers: H,
      data: { maturity_tier: 2 },
    });
  }

  await request.post(`${API_BASE}/csf/assessments/${assess.id}/approve`, {
    headers: H,
  });
  const fin = await (
    await request.post(
      `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
      { headers: H },
    )
  ).json();
  const released = await request.post(
    `${API_BASE}/csf/deliverables/${fin.id}/release`,
    { headers: H },
  );
  expect(released.ok(), "release deliverable").toBeTruthy();

  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto(`/dashboards/csf/${serviceId}`);

  await expect(
    page.getByText("Current maturity", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Target profile", { exact: true })).toBeVisible();
  await expect(page.getByText("Maturity by function")).toBeVisible();
  await expect(page.getByText("Priority remediation")).toBeVisible();

  // The truncation must be DISCLOSED, not implied. #75 is open because the ZT
  // exporter renders a slice with the true total nowhere on the page, so a
  // client reads 20 of 37 remediation items and cannot tell anything is
  // missing. Asserting the sentence, not just the list, is what stops this
  // dashboard shipping the same defect.
  await expect(
    page.getByText(/Highest-priority \d+ of \d+ gaps · \d+ more not shown/),
  ).toBeVisible();

  // All six CSF 2.0 functions render a bar.
  for (const fn of [
    "Govern",
    "Identify",
    "Protect",
    "Detect",
    "Respond",
    "Recover",
  ]) {
    await expect(page.getByText(fn, { exact: false }).first()).toBeVisible();
  }

  await page
    .screenshot({ path: "artifacts/csf-dashboard.png", fullPage: true })
    .catch(() => undefined);
});
