import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  CLIENT_EMAIL,
  CLIENT_PASSWORD,
  register,
  signIn,
  uniqueEmail,
} from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";

/**
 * SMOKE_TEST §6.7 (Sprint 5 T2): the client "WHAT YOU'VE RECEIVED" page.
 *
 * The release rule (Master Spec §12): a client sees a deliverable ONLY after a
 * consultant explicitly releases the finalized deliverable. This spec proves:
 *   1. An admin finalizes+releases a deliverable via the API; a real client of
 *      that tenant, signed in, sees the row (service label, title, Final badge)
 *      and the download link streams 200 with a §15.5 filename.
 *   2. A finalized-but-UNRELEASED deliverable never appears for the client.
 *
 * Fully ISOLATED in its own throwaway tenant (mirrors s13-isolation): it never
 * perturbs the shared seeded Atlas services other specs resolve by type, and it
 * proves the negative case (a finalized-but-unreleased deliverable stays hidden)
 * without touching the seed.
 *
 * A SECOND test proves seed → storage parity (Sprint 6 T2): the seed now writes
 * artifact bytes through get_storage() (the SAME backend the API reads — MinIO
 * under compose) and actually RELEASES its deliverables, so the real seeded
 * client (client@atlas.example) downloads a seeded released report → 200. Before
 * T2 this 410'd (bytes written to a local-FS stub the S3-backed API can't read).
 */

const TENANT_NAME = "Documents QA";
const TENANT_DOMAIN = "docsqa.example";
const PASSWORD = "correct horse battery staple!";

interface ClientRow {
  id: string;
  legal_name: string;
}

interface DeliverableRow {
  id: string;
  title: string;
  pdf_artifact_id: string | null;
  pdf_filename: string | null;
}

/** Bearer + tenant headers for admin API-direct calls. */
function tenantHeaders(
  token: string,
  clientId: string,
): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };
}

/**
 * Find-or-create the throwaway "Documents QA" tenant with a registrable,
 * approved domain — via the admin API (the endpoints the Management UI calls).
 * Idempotent against the shared DB. Returns the tenant client id.
 */
async function ensureDocsTenant(
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

test.describe("s17 /documents — released deliverables for the client", () => {
  test("empty state renders before any release (no dead ends, §12)", async ({
    page,
    request,
  }) => {
    test.slow();
    // SMOKE_TEST.md:228 (no-dead-ends rule): a client with no released
    // deliverables must see onward guidance, not a bare blank. Released
    // deliverables are per-TENANT and the shared "Documents QA" tenant
    // accumulates a released row on every prior run (the next test releases v1),
    // so the empty state can only be proven in a tenant that has never released
    // anything. Create a throwaway tenant with its own approved domain and
    // register a fresh client into it: its /documents is empty by construction.
    const token = await adminApiToken(request);
    const auth = { Authorization: `Bearer ${token}` };
    const stamp = Date.now();
    const emptyDomain = `docs-empty-${stamp}.example`;
    const created = await request.post(`${API_BASE}/admin/clients`, {
      headers: auth,
      data: { legal_name: `Documents Empty QA ${stamp}` },
    });
    expect(
      created.ok(),
      `create empty tenant (${created.status()})`,
    ).toBeTruthy();
    const emptyTenant = (await created.json()) as ClientRow;
    const approved = await request.post(
      `${API_BASE}/admin/clients/${emptyTenant.id}/domains`,
      { headers: auth, data: { domain: emptyDomain } },
    );
    expect(
      approved.status() === 201 || approved.status() === 409,
      `approve ${emptyDomain}: ${approved.status()}`,
    ).toBeTruthy();

    // A real client of the empty tenant self-registers (auto signed-in) and
    // opens /documents — no deliverable has ever been released here.
    await register(page, "Ellie Empty", uniqueEmail(emptyDomain), PASSWORD);
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
      timeout: 20000,
    });
    await page.goto("/documents");

    // The no-dead-ends empty state renders (DocumentsList EmptyState), not a
    // bare blank, with its onward-guidance copy.
    await expect(
      page.getByRole("heading", { name: "No documents yet" }),
    ).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByText(/When your SHIELD analyst releases a report/),
    ).toBeVisible();
  });

  test("client sees released deliverables + downloads; unreleased stays hidden", async ({
    page,
    request,
  }) => {
    test.slow();
    const token = await adminApiToken(request);
    const clientId = await ensureDocsTenant(request, token);
    const headers = tenantHeaders(token, clientId);

    // Open a fresh CSF service in the tenant (unique title -> deterministic rows
    // across re-runs on the shared DB).
    const serviceTitle = `Docs QA CSF ${Date.now()}`;
    const svcRes = await request.post(`${API_BASE}/csf/services`, {
      headers,
      data: { kind: "nist_csf", title: serviceTitle },
    });
    expect(svcRes.ok(), `open CSF service (${svcRes.status()})`).toBeTruthy();
    const serviceId = ((await svcRes.json()) as { id: string }).id;

    // Create + approve an assessment (approve accepts a draft directly).
    const assessRes = await request.post(
      `${API_BASE}/csf/services/${serviceId}/assessments`,
      { headers },
    );
    expect(
      assessRes.ok(),
      `create CSF assessment (${assessRes.status()})`,
    ).toBeTruthy();
    const assessmentId = ((await assessRes.json()) as { id: string }).id;
    const approveRes = await request.post(
      `${API_BASE}/csf/assessments/${assessmentId}/approve`,
      { headers },
    );
    expect(
      approveRes.ok(),
      `approve assessment (${approveRes.status()})`,
    ).toBeTruthy();

    // Finalize v1 and RELEASE it (the positive case).
    const fin1 = await request.post(
      `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
      { headers },
    );
    expect(fin1.status(), `finalize v1 (${await fin1.text()})`).toBe(201);
    const v1 = (await fin1.json()) as DeliverableRow;
    const release = await request.post(
      `${API_BASE}/csf/deliverables/${v1.id}/release`,
      { headers },
    );
    expect(release.ok(), `release v1 (${release.status()})`).toBeTruthy();

    // Finalize v2 but LEAVE IT UNRELEASED (the negative case).
    const fin2 = await request.post(
      `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
      { headers },
    );
    expect(fin2.status(), `finalize v2 (${await fin2.text()})`).toBe(201);
    const v2 = (await fin2.json()) as DeliverableRow;

    // A real client of this tenant self-registers (auto signed-in) and opens
    // /documents.
    await register(page, "Dana Docs", uniqueEmail(TENANT_DOMAIN), PASSWORD);
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
      timeout: 20000,
    });
    await page.goto("/documents");

    // Client nav gained the Documents entry.
    await expect(page.getByRole("link", { name: "Documents" })).toBeVisible({
      timeout: 20000,
    });

    // The released v1 row is present with its service label + Final badge.
    const table = page.getByRole("table");
    await expect(table).toBeVisible({ timeout: 20000 });
    const row = page.getByRole("row").filter({ hasText: v1.title });
    await expect(row).toBeVisible();
    await expect(row.getByText("NIST CSF 2.0 Assessment")).toBeVisible();
    await expect(row.getByText("Final", { exact: true })).toBeVisible();

    // The unreleased v2 deliverable is absent from the page.
    await expect(page.getByText(v2.title, { exact: true })).toHaveCount(0);

    // The client's own download link streams 200 with a §15.5 filename.
    expect(
      v1.pdf_artifact_id,
      "released deliverable has a PDF artifact",
    ).toBeTruthy();
    expect(v1.pdf_filename ?? "").toMatch(
      /_NIST_CSF_2_0_Assessment\d{6}(?:_v\d+)?\.pdf$/,
    );
    const download = await page.request.get(
      `/api/proxy/artifacts/${v1.pdf_artifact_id}/download`,
    );
    expect(download.status(), "client PDF download status").toBe(200);
    expect(download.headers()["content-type"]).toContain("application/pdf");
    expect(download.headers()["content-disposition"] ?? "").toContain(
      v1.pdf_filename ?? "__no_filename__",
    );
    const body = await download.body();
    expect(body.length, "PDF byte size").toBeGreaterThan(0);
  });

  test("seeded Atlas client downloads a SEEDED released deliverable (T2 storage parity)", async ({
    page,
    request,
  }) => {
    test.slow();
    // Resolve a seeded released deliverable straight from the API (admin-direct,
    // tenant-scoped by X-Client-Id) so we know its artifact id + §15.5 filename.
    const token = await adminApiToken(request);
    const clientId = await atlasClientIdViaApi(request, token);
    const listed = await request.get(
      `${API_BASE}/clients/${clientId}/deliverables`,
      {
        headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId },
      },
    );
    expect(
      listed.ok(),
      `list seeded deliverables (${listed.status()})`,
    ).toBeTruthy();
    const items = ((await listed.json()) as { items: DeliverableRow[] }).items;
    const seeded = items.find((d) => d.pdf_artifact_id);
    expect(
      seeded,
      "seed must release at least one deliverable with a PDF artifact",
    ).toBeTruthy();
    const deliverable = seeded as DeliverableRow;

    // The REAL seeded client of the Atlas tenant signs in and opens /documents.
    await signIn(page, CLIENT_EMAIL, CLIENT_PASSWORD);
    await page.goto("/documents");
    const table = page.getByRole("table");
    await expect(table).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByRole("row").filter({ hasText: deliverable.title }),
    ).toBeVisible();

    // The seeded deliverable's bytes are in the SAME store the API reads: the
    // client download streams 200 (this 410'd before the seed→storage fix).
    const download = await page.request.get(
      `/api/proxy/artifacts/${deliverable.pdf_artifact_id}/download`,
    );
    expect(download.status(), "seeded PDF download status").toBe(200);
    expect(download.headers()["content-type"]).toContain("application/pdf");
    expect(download.headers()["content-disposition"] ?? "").toContain(
      deliverable.pdf_filename ?? "__no_filename__",
    );
    const body = await download.body();
    expect(body.length, "seeded PDF byte size").toBeGreaterThan(0);
  });
});
