import { expect, test, type APIRequestContext } from "@playwright/test";

import { signIn, uniqueEmail } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";

/**
 * D-035 / D-106: once the admin generates and PUBLISHES the Risk Register, the
 * client can open its dashboard (5x5 matrix + tier mix + full register),
 * reached via a link on /results.
 *
 * #737 REWRITE, and why it no longer uses the seeded Atlas tenant. Publication
 * now needs every input the client has engaged to be RELEASED (Gene's ruling,
 * #736 item 13). Atlas is seeded with its CSF at v2 APPROVED-not-released on
 * purpose (the CSF dashboard specs depend on it), and this spec used to leave
 * draft ATT&CK and ZT assessments on Atlas too, so Atlas cannot be published
 * from here without mutating shared seed state. So the spec seeds its own
 * precondition (the s34 pattern): a fresh tenant, a mapped domain, a client
 * user, and that tenant's ATT&CK and ZT inputs, released through the real
 * finalize -> release endpoints.
 *
 * It also asserts that publish REFUSES before the release step: the cheapest
 * proof that this spec runs Gene's gate rather than walking around it.
 */

const PASSWORD = "correct horse battery staple!";

function tenantHeaders(
  token: string,
  clientId: string,
): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };
}

async function createTenant(
  request: APIRequestContext,
  token: string,
): Promise<{ clientId: string; domain: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const stamp = Date.now();
  const created = await request.post(`${API_BASE}/admin/clients`, {
    headers: auth,
    data: { legal_name: `Risk QA ${stamp}` },
  });
  expect(created.ok(), `create tenant (${created.status()})`).toBeTruthy();
  const clientId = ((await created.json()) as { id: string }).id;
  const domain = `riskqa-${stamp}.example`;
  const mapped = await request.post(
    `${API_BASE}/admin/clients/${clientId}/domains`,
    {
      headers: auth,
      data: { domain },
    },
  );
  expect(mapped.status(), `approve ${domain}`).toBe(201);
  return { clientId, domain };
}

/** Finalize then release one service's deliverable (prefix: attack | zt). */
async function release(
  request: APIRequestContext,
  headers: Record<string, string>,
  prefix: "attack" | "zt",
  serviceId: string,
): Promise<void> {
  const fin = await request.post(
    `${API_BASE}/${prefix}/services/${serviceId}/deliverables/finalize`,
    { headers },
  );
  expect(fin.ok(), `finalize ${prefix}: ${await fin.text()}`).toBeTruthy();
  const deliverableId = ((await fin.json()) as { id: string }).id;
  const rel = await request.post(
    `${API_BASE}/${prefix}/deliverables/${deliverableId}/release`,
    {
      headers,
    },
  );
  expect(rel.ok(), `release ${prefix}: ${await rel.text()}`).toBeTruthy();
}

test("client views the published Risk Register dashboard", async ({
  page,
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const { clientId: cid, domain } = await createTenant(request, token);
  const H = tenantHeaders(token, cid);

  // The client user, registered under the tenant's approved domain.
  const clientEmail = uniqueEmail(domain);
  const reg = await request.post("/api/proxy/auth/register", {
    data: {
      email: clientEmail,
      password: PASSWORD,
      display_name: "Riley Risk",
    },
  });
  expect(reg.status(), await reg.text()).toBe(201);

  // An ATT&CK gap + a low ZT answer, both APPROVED, to unlock the gate.
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
  // A STANDALONE technique: the first row, T1001, has sub-techniques, and
  // since #554 (D-094) its status is computed and a PATCH to it is refused.
  const rows = aAssess.coverage as { id: string; technique_code: string }[];
  const standalone = rows.find(
    (c) =>
      !c.technique_code.includes(".") &&
      !rows.some((o) => o.technique_code.startsWith(`${c.technique_code}.`)),
  );
  expect(standalone, "no standalone ATT&CK technique").toBeTruthy();
  const gapRes = await request.patch(
    `${API_BASE}/attack/coverage/${standalone?.id}`,
    {
      headers: H,
      data: { status: "gap" },
    },
  );
  expect(gapRes.ok(), await gapRes.text()).toBe(true);
  const aApprove = await request.post(
    `${API_BASE}/attack/assessments/${aAssess.id}/approve`,
    {
      headers: H,
    },
  );
  expect(aApprove.ok(), await aApprove.text()).toBe(true);

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
  const zAnswer = await request.patch(
    `${API_BASE}/zt/answers/${zAssess.answers[0].id}`,
    {
      headers: H,
      data: { maturity_stage: 1 },
    },
  );
  expect(zAnswer.ok(), await zAnswer.text()).toBe(true);
  const zApprove = await request.post(
    `${API_BASE}/zt/assessments/${zAssess.id}/approve`,
    {
      headers: H,
    },
  );
  expect(zApprove.ok(), await zApprove.text()).toBe(true);

  // Generated from APPROVED, not-yet-released inputs: a draft. Publish refuses
  // it and names the inputs -- Gene's gate, observed rather than assumed.
  const draftGen = await request.post(
    `${API_BASE}/risk/clients/${cid}/register/generate`,
    {
      headers: H,
    },
  );
  expect(
    draftGen.ok(),
    `generate (draft): ${await draftGen.text()}`,
  ).toBeTruthy();
  const refused = await request.post(
    `${API_BASE}/risk/clients/${cid}/register/publish`,
    {
      headers: H,
    },
  );
  expect(refused.status(), await refused.text()).toBe(409);
  const refusal = (await refused.json()) as {
    error: { reason: string; blockers: { input: string }[] };
  };
  expect(refusal.error.reason).toBe("risk_register_inputs_not_final");
  expect(refusal.error.blockers.map((b) => b.input).sort()).toEqual([
    "attack",
    "zt",
  ]);

  // Release both inputs, generate from the released work, publish.
  await release(request, H, "attack", asvc.id);
  await release(request, H, "zt", zsvc.id);
  const gen = await request.post(
    `${API_BASE}/risk/clients/${cid}/register/generate`,
    {
      headers: H,
    },
  );
  expect(gen.ok(), `generate: ${await gen.text()}`).toBeTruthy();
  const pub = await request.post(
    `${API_BASE}/risk/clients/${cid}/register/publish`,
    {
      headers: H,
    },
  );
  expect(pub.ok(), `publish register: ${await pub.text()}`).toBeTruthy();

  await signIn(page, clientEmail, PASSWORD);

  // The Risk Register link surfaces on /results once published.
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
