import { expect, test } from "@playwright/test";

import { CLIENT_EMAIL, CLIENT_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * D-035: after an admin releases a MITRE ATT&CK deliverable, the client can open
 * an interactive coverage dashboard. Setup drives the admin API directly (open
 * service -> assess a covered/partial/gap mix -> approve -> finalize -> release);
 * the client then views the dashboard through the real UI.
 */

test("client views a released MITRE ATT&CK coverage dashboard", async ({
  page,
  request,
}) => {
  // --- Admin API setup: a released ATT&CK service under the Atlas tenant. ---
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const H = { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };

  const svc = await (
    await request.post(`${API_BASE}/attack/services`, {
      headers: H,
      data: { kind: "attack_coverage", title: "E2E ATT&CK Dashboard" },
    })
  ).json();
  const serviceId = svc.id as string;

  const assess = await (
    await request.post(`${API_BASE}/attack/services/${serviceId}/assessments`, {
      headers: H,
    })
  ).json();
  const coverage = assess.coverage as { id: string }[];

  const pattern = [
    ...Array(6).fill("covered"),
    ...Array(4).fill("partial"),
    ...Array(3).fill("gap"),
  ];
  for (let i = 0; i < pattern.length; i++) {
    const status = pattern[i];
    const body: Record<string, unknown> = { status };
    if (status === "covered") {
      Object.assign(body, {
        detection_tools: ["CrowdStrike Falcon"],
        prevention_tools: ["STIG baselines"],
        response_tools: ["Cortex XSOAR"],
        rationale: "Full detect/prevent/respond triad in place.",
      });
    } else if (status === "gap") {
      body.rationale = "Container runtime detection gap — no coverage today.";
    }
    await request.patch(`${API_BASE}/attack/coverage/${coverage[i].id}`, {
      headers: H,
      data: body,
    });
  }

  await request.post(`${API_BASE}/attack/assessments/${assess.id}/approve`, {
    headers: H,
  });
  const fin = await (
    await request.post(
      `${API_BASE}/attack/services/${serviceId}/deliverables/finalize`,
      { headers: H },
    )
  ).json();
  const released = await request.post(
    `${API_BASE}/attack/deliverables/${fin.id}/release`,
    { headers: H },
  );
  expect(released.ok(), "release deliverable").toBeTruthy();

  // --- Client views the dashboard through the UI. ---
  await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
  await page.goto(`/dashboards/attack/${serviceId}`);

  // KPI cards (exact — "Fully covered" also appears in the D/P/R blurb).
  await expect(
    page.getByText("Techniques evaluated", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Fully covered", { exact: true })).toBeVisible();
  await expect(page.getByText("Blind spots", { exact: true })).toBeVisible();

  // Sections + the uncovered technique cards (3 gaps seeded).
  await expect(page.getByText(/blind to today/i)).toBeVisible();
  await expect(page.getByText("Per-technique coverage matrix")).toBeVisible();
  await expect(page.getByPlaceholder(/Search technique/i)).toBeVisible();

  // Both charts (tactic bar + coverage-mix donut) mount client-side via a
  // dynamic import of Chart.js — wait for their canvases before asserting.
  await expect(page.locator("canvas")).toHaveCount(2);

  // The matrix is filterable: narrow to Uncovered and confirm rows remain.
  await page.getByLabel("Filter by coverage").selectOption("gap");
  await expect(page.getByText("Uncovered").first()).toBeVisible();

  // Give Chart.js a beat to paint, then capture the artifact.
  await page.waitForTimeout(1200);
  await page
    .screenshot({ path: "artifacts/attack-dashboard.png", fullPage: true })
    .catch(() => undefined);
});
