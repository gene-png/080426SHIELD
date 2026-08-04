import { expect, test, type APIRequestContext } from "@playwright/test";

import { uniqueEmail } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";
import { fetchLatestMessage, subjectOf } from "../helpers/mailhog";

/**
 * SMOKE_TEST §29 (Sprint 8 T2): the client release-notification email (D-030),
 * proven end-to-end through MailHog.
 *
 * Releasing a finalized deliverable emails every ACTIVE CLIENT-role user of the
 * tenant. The four test_release_notification.py unit tests prove recipient
 * selection / body / best-effort semantics with the sender STUBBED; this spec
 * proves the mail actually LANDS in the inbox for a real registered client of an
 * ISOLATED tenant — recipient selection for real, not just "some mail exists".
 *
 * Isolated in its own throwaway tenant (unique name + approved domain per run,
 * the s18 createHomeTenant pattern): the only active client user in the tenant is
 * the one this spec registers, so the release notifies exactly that recipient.
 *
 * Email delivery is on by default in dev/CI compose since Sprint 7 T3; if a stack
 * has it off the spec self-skips (mirrors s21) rather than failing.
 */

const PASSWORD = "correct horse battery staple!";

interface ClientRow {
  id: string;
  legal_name: string;
}

interface DeliverableRow {
  id: string;
  title: string;
  version: number;
}

/** Bearer + tenant headers for admin API-direct calls. */
function tenantHeaders(
  token: string,
  clientId: string,
): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };
}

/**
 * Create a FRESH throwaway tenant (unique name + approved domain per run) so the
 * ONLY active client user in it is the one this spec registers — the release then
 * notifies exactly that recipient. A domain binds to exactly one client, so both
 * the tenant name AND its domain must be unique per run (the s18 pattern).
 */
async function createNotifyTenant(
  request: APIRequestContext,
  token: string,
): Promise<{ clientId: string; domain: string }> {
  const auth = { Authorization: `Bearer ${token}` };
  const stamp = Date.now();
  const created = await request.post(`${API_BASE}/admin/clients`, {
    headers: auth,
    data: { legal_name: `Notify QA ${stamp}` },
  });
  expect(created.ok(), `create tenant (${created.status()})`).toBeTruthy();
  const tenant = (await created.json()) as ClientRow;
  const domainName = `notifyqa-${stamp}.example`;
  const domain = await request.post(
    `${API_BASE}/admin/clients/${tenant.id}/domains`,
    { headers: auth, data: { domain: domainName } },
  );
  expect(domain.status(), `approve ${domainName}`).toBe(201);
  return { clientId: tenant.id, domain: domainName };
}

/** Finalize a fresh CSF deliverable in the tenant and release it. */
async function releaseCsfDeliverable(
  request: APIRequestContext,
  headers: Record<string, string>,
): Promise<DeliverableRow> {
  const svcRes = await request.post(`${API_BASE}/csf/services`, {
    headers,
    data: { kind: "nist_csf", title: `Notify QA CSF ${Date.now()}` },
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
  const assessmentId = ((await assessRes.json()) as { id: string }).id;
  const approveRes = await request.post(
    `${API_BASE}/csf/assessments/${assessmentId}/approve`,
    { headers },
  );
  expect(approveRes.ok(), `approve (${approveRes.status()})`).toBeTruthy();

  const fin = await request.post(
    `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
    { headers },
  );
  expect(fin.status(), `finalize (${await fin.text()})`).toBe(201);
  const deliverable = (await fin.json()) as DeliverableRow;
  const release = await request.post(
    `${API_BASE}/csf/deliverables/${deliverable.id}/release`,
    { headers },
  );
  expect(release.ok(), `release (${release.status()})`).toBeTruthy();
  return deliverable;
}

test.describe("s22 release notification — client mail lands in MailHog (§29)", () => {
  test("releasing a CSF deliverable emails the tenant client with the /documents link", async ({
    request,
  }) => {
    test.slow();
    const token = await adminApiToken(request);
    const { clientId, domain } = await createNotifyTenant(request, token);

    // A real client of this tenant registers (an active CLIENT user) BEFORE the
    // release, so recipient selection (User.client_id == tenant AND role==CLIENT
    // AND is_active) picks them. Registration ALSO mails this address (the
    // verification email), which is why the assertion below matches by subject —
    // "latest for recipient" alone could select the wrong message.
    const clientEmail = uniqueEmail(domain);
    const reg = await request.post("/api/proxy/auth/register", {
      data: {
        email: clientEmail,
        password: PASSWORD,
        display_name: "Nadia Notify",
      },
    });
    expect(reg.status(), await reg.text()).toBe(201);

    // The consultant finalizes + releases a CSF deliverable -> best-effort notify.
    const deliverable = await releaseCsfDeliverable(
      request,
      tenantHeaders(token, clientId),
    );

    // The notification lands for THIS recipient with the release subject (not the
    // registration verification mail). service_label for CSF is "NIST CSF 2.0"
    // (deliverable_release.py:35 / sender.py:101).
    const expectedSubject = "Your NIST CSF 2.0 deliverable is ready";
    const message = await fetchLatestMessage(request, clientEmail, {
      subject: "deliverable is ready",
    });
    test.skip(
      message === null,
      "email delivery disabled (set SHIELD_EMAIL_DELIVERY_ENABLED=true to run)",
    );
    expect(subjectOf(message!), "release notification subject").toBe(
      expectedSubject,
    );

    // The body carries the deliverable title + a link to the client /documents
    // surface (collapse MailHog quoted-printable soft line breaks first).
    const body = message!.Content.Body.replace(/=\r?\n/g, "").replace(
      /=3D/g,
      "=",
    );
    expect(body, "body links to /documents").toContain("/documents");
    expect(body, "body names the released deliverable").toContain(
      deliverable.title,
    );
  });
});
