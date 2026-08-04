import { expect, test, type APIRequestContext } from "@playwright/test";

import { register, uniqueEmail } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";

/**
 * SMOKE_TEST §2.5 (Sprint 5 T4): the cross-service value-loop card on /home.
 *
 * Proves the deterministic executive summary:
 *   1. Before any report is released, /home shows no value card (the guidance
 *      state from s18 stands alone).
 *   2. After an admin scores a CSF assessment with real gaps and finalizes +
 *      releases it, the same client's /home shows the value card with a NIST CSF
 *      gap count and "Pending" for the services with no released data yet.
 *   3. §6.4 still holds — the card leaks no scoring math: no percentage renders.
 *
 * Isolated in its own throwaway tenant (mirrors s17/s18): the release/download
 * path needs a runtime-finalized deliverable, and a fresh tenant keeps the
 * "no card before release" assertion honest across re-runs.
 */

const PASSWORD = "correct horse battery staple!";

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

async function createValueTenant(
  request: APIRequestContext,
  token: string,
): Promise<{ clientId: string; domain: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const stamp = Date.now();
  const created = await request.post(`${API_BASE}/admin/clients`, {
    headers: auth,
    data: { legal_name: `Value QA ${stamp}` },
  });
  expect(created.ok(), `create tenant (${created.status()})`).toBeTruthy();
  const tenant = (await created.json()) as ClientRow;
  const domainName = `valueqa-${stamp}.example`;
  const domain = await request.post(
    `${API_BASE}/admin/clients/${tenant.id}/domains`,
    { headers: auth, data: { domain: domainName } },
  );
  expect(domain.status(), `approve ${domainName}`).toBe(201);
  return { clientId: tenant.id, domain: domainName };
}

/**
 * Open a CSF service, score three subcategories below the tier-3 target (real
 * gaps), approve, finalize, and release.
 */
async function releaseScoredCsf(
  request: APIRequestContext,
  headers: Record<string, string>,
): Promise<void> {
  const svcRes = await request.post(`${API_BASE}/csf/services`, {
    headers,
    data: { kind: "nist_csf", title: `Value QA CSF ${Date.now()}` },
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
  const assessment = (await assessRes.json()) as {
    id: string;
    answers: { id: string }[];
  };
  // Score three subcategories at tier 1 -> guaranteed gaps against tier 3.
  for (const ans of assessment.answers.slice(0, 3)) {
    const patch = await request.patch(`${API_BASE}/csf/answers/${ans.id}`, {
      headers,
      data: { maturity_tier: 1 },
    });
    expect(patch.ok(), `score answer (${patch.status()})`).toBeTruthy();
  }

  const approveRes = await request.post(
    `${API_BASE}/csf/assessments/${assessment.id}/approve`,
    { headers },
  );
  expect(approveRes.ok(), `approve (${approveRes.status()})`).toBeTruthy();

  const fin = await request.post(
    `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
    { headers },
  );
  expect(fin.status(), `finalize (${await fin.text()})`).toBe(201);
  const deliverable = (await fin.json()) as { id: string };
  const release = await request.post(
    `${API_BASE}/csf/deliverables/${deliverable.id}/release`,
    { headers },
  );
  expect(release.ok(), `release (${release.status()})`).toBeTruthy();
}

test.describe("s19 /home — cross-service value-loop card (§2.5)", () => {
  test("no card before release, CSF gap count after, no scoring math leaks", async ({
    page,
    request,
  }) => {
    test.slow();
    const token = await adminApiToken(request);
    const { clientId, domain } = await createValueTenant(request, token);

    await register(page, "Vera Value", uniqueEmail(domain), PASSWORD);
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
      timeout: 20000,
    });

    // Before any release: no value card.
    await page.goto("/home");
    await expect(
      page.getByRole("heading", { name: /Welcome back/ }),
    ).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByRole("heading", { name: "Your engagement at a glance" }),
    ).toHaveCount(0);

    // Admin scores + releases a CSF report for this tenant.
    await releaseScoredCsf(request, tenantHeaders(token, clientId));

    // After release: the value card renders with a CSF gap count.
    await page.goto("/home");
    await expect(
      page.getByRole("heading", { name: "Your engagement at a glance" }),
    ).toBeVisible({ timeout: 20000 });
    // exact: true — getByText is substring, and "NIST CSF 2.0" also appears in
    // the hero heading, the service grid, and the activity feed. The card's
    // metric label is the only exact match.
    await expect(page.getByText("NIST CSF 2.0", { exact: true })).toBeVisible();
    await expect(page.getByText(/gaps? to close/)).toBeVisible();
    // Services with no released data yet read "Pending", never a fake 0.
    await expect(page.getByText("Pending").first()).toBeVisible();

    // §6.4: the card must not leak scoring math — no percentage anywhere.
    await expect(page.getByText(/\d+%/)).toHaveCount(0);
  });
});
