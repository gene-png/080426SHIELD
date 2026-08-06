import { expect, test } from "@playwright/test";

import { CLIENT_EMAIL, CLIENT_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * D-035: once the admin generates and finalizes (exports) the Risk Register, the
 * client can open its dashboard (5x5 matrix + tier mix + full register). The
 * register is client-level, reached via a link on /results.
 */

test("client views the finalized Risk Register dashboard", async ({
  page,
  request,
}) => {
  const token = await adminApiToken(request);
  const cid = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": cid };

  // Seed an ATT&CK gap + a low ZT answer to unlock the risk gate.
  const asvc = await (
    await request.post(`${API_BASE}/attack/services`, {
      headers: H,
      data: { kind: "attack_coverage", title: "E2E Risk ATT&CK" },
    })
  ).json();
  const aAssess = await (
    await request.post(`${API_BASE}/attack/services/${asvc.id}/assessments`, {
      headers: H,
    })
  ).json();
  await request.patch(`${API_BASE}/attack/coverage/${aAssess.coverage[0].id}`, {
    headers: H,
    data: { status: "gap" },
  });

  const zsvc = await (
    await request.post(`${API_BASE}/zt/services`, {
      headers: H,
      data: { kind: "zero_trust_cisa", title: "E2E Risk ZT" },
    })
  ).json();
  const zAssess = await (
    await request.post(`${API_BASE}/zt/services/${zsvc.id}/assessments`, {
      headers: H,
    })
  ).json();
  await request.patch(`${API_BASE}/zt/answers/${zAssess.answers[0].id}`, {
    headers: H,
    data: { maturity_stage: 1 },
  });

  const gen = await request.post(
    `${API_BASE}/risk/clients/${cid}/register/generate`,
    {
      headers: H,
    },
  );
  expect(gen.ok(), "generate register").toBeTruthy();
  const exp = await request.post(
    `${API_BASE}/risk/clients/${cid}/register/export`,
    {
      headers: H,
    },
  );
  expect(exp.ok(), "export (finalize) register").toBeTruthy();

  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);

  // The Risk Register link surfaces on /results once finalized.
  await page.goto("/results");
  await expect(page.getByText("View Risk Register dashboard →")).toBeVisible();
  await page.getByText("View Risk Register dashboard →").click();
  await page.waitForURL((url) => url.pathname.includes("/dashboards/risk"));

  await expect(page.getByText("Open risks", { exact: true })).toBeVisible();
  await expect(page.getByText("Likelihood × Impact matrix")).toBeVisible();
  await expect(page.getByText("Full register")).toBeVisible();

  // The tier-mix doughnut mounts client-side.
  await expect(page.locator("canvas")).toHaveCount(1);

  await page.waitForTimeout(1200);
  await page
    .screenshot({ path: "artifacts/risk-dashboard.png", fullPage: true })
    .catch(() => undefined);
});
