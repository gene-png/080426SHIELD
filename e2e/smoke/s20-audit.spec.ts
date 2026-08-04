import { expect, test, type APIRequestContext } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";

/**
 * SMOKE_TEST §11 (Sprint 5 T7): the /admin/audit viewer.
 *
 * audit_entries and llm_calls are append-only stores with many write sites and
 * (until T7) no read surface. This spec proves the read-only two-tab viewer:
 *   1. An audited action performed in-test (a CSF run-ai) appears in the
 *      Activity tab (action "csf.run_ai").
 *   2. The AI calls tab lists the fixture-mode llm_calls row it created
 *      (purpose csf_score, fixture mode).
 *   3. Correlation-id click-through links the two tabs: clicking the AI call's
 *      correlation jumps to Activity filtered by that id, surfacing the
 *      csf.run_ai audit row written in the same request.
 *
 * ISOLATED in a throwaway "Audit QA" tenant so it never perturbs the shared
 * seeded services other specs resolve by type. Run-ai is fixture-mode
 * deterministic (D-017), so the llm_calls row is always written.
 */

const TENANT_NAME = "Audit QA";
const TENANT_DOMAIN = "auditqa.example";

interface ClientRow {
  id: string;
  legal_name: string;
}

function tenantHeaders(
  token: string,
  clientId: string,
): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };
}

async function ensureAuditTenant(
  request: APIRequestContext,
  token: string,
): Promise<string> {
  const auth = { Authorization: `Bearer ${token}` };
  const listed = await request.get(`${API_BASE}/admin/clients`, {
    headers: auth,
  });
  expect(listed.ok()).toBeTruthy();
  const clients = ((await listed.json()) as { clients: ClientRow[] }).clients;
  let tenant = clients.find(
    (c) => c.legal_name.toLowerCase() === TENANT_NAME.toLowerCase(),
  );
  if (!tenant) {
    const created = await request.post(`${API_BASE}/admin/clients`, {
      headers: auth,
      data: { legal_name: TENANT_NAME },
    });
    expect(created.ok()).toBeTruthy();
    tenant = (await created.json()) as ClientRow;
  }
  const domain = await request.post(
    `${API_BASE}/admin/clients/${tenant.id}/domains`,
    { headers: auth, data: { domain: TENANT_DOMAIN } },
  );
  expect(
    domain.status() === 201 || domain.status() === 409,
    `approve ${TENANT_DOMAIN}: ${domain.status()}`,
  ).toBeTruthy();
  return tenant.id;
}

test.describe("s20 /admin/audit — read-only audit viewer", () => {
  test("activity + AI-call rows render; correlation links the tabs", async ({
    page,
    request,
  }) => {
    test.slow();
    const token = await adminApiToken(request);
    const clientId = await ensureAuditTenant(request, token);
    const headers = tenantHeaders(token, clientId);

    // Open a fresh CSF service + assessment, seed the Working Profile, then run
    // the fixture-mode AI job. That single request writes ONE llm_calls row
    // (purpose csf_score) AND one audit row (action csf.run_ai) sharing a
    // correlation id — exactly the pair the viewer must link.
    const serviceTitle = `Audit QA CSF ${Date.now()}`;
    const svcRes = await request.post(`${API_BASE}/csf/services`, {
      headers,
      data: { kind: "nist_csf", title: serviceTitle },
    });
    expect(svcRes.ok(), `open CSF service (${svcRes.status()})`).toBeTruthy();
    const serviceId = ((await svcRes.json()) as { id: string }).id;

    const assessRes = await request.post(
      `${API_BASE}/csf/services/${serviceId}/assessments`,
      { headers },
    );
    expect(
      assessRes.ok(),
      `create assessment (${assessRes.status()})`,
    ).toBeTruthy();

    const seedRes = await request.post(
      `${API_BASE}/csf/services/${serviceId}/profiles/seed`,
      { headers, data: { tiers: ["moderate"] } },
    );
    expect(seedRes.ok(), `seed profiles (${seedRes.status()})`).toBeTruthy();

    const runRes = await request.post(
      `${API_BASE}/csf/services/${serviceId}/run-ai`,
      { headers },
    );
    expect(
      runRes.ok(),
      `run-ai (${runRes.status()} ${await runRes.text()})`,
    ).toBeTruthy();

    // Sign in as the admin and open the viewer.
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/audit");

    // The admin nav gained an Audit entry, and the page renders.
    await expect(page.getByRole("link", { name: "Audit" }).first()).toBeVisible(
      {
        timeout: 20000,
      },
    );
    await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible({
      timeout: 20000,
    });

    // Activity tab (default): filter to our audited action and see the row.
    await page.getByTestId("audit-filter-action").fill("csf.run_ai");
    await page.getByTestId("audit-apply-activity").click();
    const activityTable = page.getByTestId("audit-activity-table");
    await expect(
      activityTable.getByText("csf.run_ai", { exact: true }).first(),
    ).toBeVisible({ timeout: 20000 });

    // AI calls tab: our fixture-mode csf_score row is listed.
    await page.getByTestId("audit-tab-ai").click();
    await page.getByTestId("audit-filter-purpose").fill("csf_score");
    await page.getByTestId("audit-apply-ai").click();
    const aiTable = page.getByTestId("audit-ai-table");
    await expect(
      aiTable.getByText("csf_score", { exact: true }).first(),
    ).toBeVisible({ timeout: 20000 });
    await expect(aiTable.getByText(/fixture/).first()).toBeVisible();

    // Correlation click-through: clicking an AI call's correlation id jumps to
    // the Activity tab filtered by that id, surfacing the linked audit row.
    await aiTable.getByTestId("audit-corr-link").first().click();
    await expect(page.getByTestId("audit-clear-correlation")).toBeVisible({
      timeout: 20000,
    });
    await expect(
      page
        .getByTestId("audit-activity-table")
        .getByText("csf.run_ai", { exact: true })
        .first(),
    ).toBeVisible({ timeout: 20000 });
  });
});
