import {
  expect,
  test,
  type APIRequestContext,
  type Page,
  type Route,
} from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE } from "../helpers/ids";

/**
 * RR-2 (for #1121): the Risk Register, Deliverables and Messages pages take
 * their client from their own picker and the URL's `?client=`, never from the
 * shared active-client cookie alone. Design note rev 12, §6.1.
 *
 * Throughout, the COOKIE names tenant A and the page is asked for tenant B, so
 * anything that still reads the cookie is answered for the wrong tenant and
 * shows up as A. Apply writes no cookie, so the spec reads the cookie back as
 * A after each step: a regression that wrote it would otherwise make these
 * pass for the wrong reason.
 *
 * Copy is the advisor's approved wording (#736 6133670854), spelled out.
 */

test.describe.configure({ timeout: 300_000 });

const ACTIVE_CLIENT_COOKIE = "shield_active_client_id";
const SWITCH_WINDOW_MS = 3_000;
const string18 = (label: string) =>
  `Opening ${label}. If this page does not change, reload it, then choose the client again.`;

interface Tenant {
  id: string;
  name: string;
}

/** One word, so its filename slug is the name itself. */
async function createTenant(
  request: APIRequestContext,
  token: string,
  prefix: string,
): Promise<Tenant> {
  const name = `${prefix}${Date.now()}`;
  const res = await request.post(`${API_BASE}/admin/clients`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { legal_name: name },
  });
  expect(res.ok(), `create tenant (${res.status()})`).toBeTruthy();
  return { id: ((await res.json()) as { id: string }).id, name };
}

function headers(token: string, clientId: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "X-Client-Id": clientId };
}

async function openService(
  request: APIRequestContext,
  h: Record<string, string>,
  prefix: "attack" | "zt" | "csf",
  kind: string,
  title: string,
): Promise<string> {
  const svc = await request.post(`${API_BASE}/${prefix}/services`, {
    headers: h,
    data: { kind, title },
  });
  expect(svc.ok(), `open ${kind} (${await svc.text()})`).toBeTruthy();
  const id = ((await svc.json()) as { id: string }).id;
  const a = await request.post(
    `${API_BASE}/${prefix}/services/${id}/assessments`,
    { headers: h },
  );
  expect(a.ok(), `assessment for ${kind} (${await a.text()})`).toBeTruthy();
  return id;
}

/** A CSF deliverable with its files, as s40 builds one. */
async function finalizeCsfDeliverable(
  request: APIRequestContext,
  h: Record<string, string>,
  title: string,
): Promise<void> {
  const svc = await request.post(`${API_BASE}/csf/services`, {
    headers: h,
    data: { kind: "nist_csf", title },
  });
  expect(svc.ok(), `open CSF (${svc.status()})`).toBeTruthy();
  const serviceId = ((await svc.json()) as { id: string }).id;
  const assessment = await request.post(
    `${API_BASE}/csf/services/${serviceId}/assessments`,
    { headers: h },
  );
  expect(assessment.ok(), "create assessment").toBeTruthy();
  const assessmentId = ((await assessment.json()) as { id: string }).id;
  const approve = await request.post(
    `${API_BASE}/csf/assessments/${assessmentId}/approve`,
    { headers: h },
  );
  expect(approve.ok(), "approve").toBeTruthy();
  const fin = await request.post(
    `${API_BASE}/csf/services/${serviceId}/deliverables/finalize`,
    { headers: h },
  );
  expect(fin.status(), `finalize (${await fin.text()})`).toBe(201);
}

/** A generated and exported register, so its download links exist. */
async function exportedRegister(page: Page, cid: string): Promise<void> {
  const gen = await page.request.post(
    `/api/proxy/risk/clients/${cid}/register/generate`,
  );
  expect(gen.ok(), `generate (${await gen.text()})`).toBeTruthy();
  const exp = await page.request.post(
    `/api/proxy/risk/clients/${cid}/register/export`,
    { timeout: 180_000 },
  );
  expect(exp.ok(), `export (${await exp.text()})`).toBeTruthy();
}

async function setCookieClient(page: Page, clientId: string): Promise<void> {
  const res = await page.request.post("/api/active-client", {
    data: { clientId },
  });
  expect(res.ok(), "set the saved client").toBeTruthy();
}

async function cookieClient(page: Page): Promise<string | undefined> {
  const all = await page.context().cookies();
  return all.find((c) => c.name === ACTIVE_CLIENT_COOKIE)?.value;
}

function urlClient(page: Page): string | null {
  return new URL(page.url()).searchParams.get("client");
}

/** GETs the page made, by path, counted since the listener was attached. */
function countRequests(page: Page): (path: string) => number {
  const seen: string[] = [];
  page.on("request", (req) => {
    if (req.method() === "GET") seen.push(new URL(req.url()).pathname);
  });
  return (path) => seen.filter((p) => p === path).length;
}

async function mountedAt(page: Page): Promise<string | null> {
  return page
    .locator("[data-mounted-at]")
    .first()
    .getAttribute("data-mounted-at");
}

test("the picker's client, not the cookie's, reaches the URL, a reload, the twin page and both downloads", async ({
  page,
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const A = await createTenant(request, token, "RRTwoA");
  const B = await createTenant(request, token, "RRTwoB");
  for (const t of [A, B]) {
    const h = headers(token, t.id);
    await openService(
      request,
      h,
      "attack",
      "attack_coverage",
      `${t.name} ATT&CK`,
    );
    await openService(request, h, "zt", "zero_trust_cisa", `${t.name} ZT`);
    await finalizeCsfDeliverable(request, h, `${t.name} CSF`);
  }

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  for (const t of [A, B]) await exportedRegister(page, t.id);
  await setCookieClient(page, A.id);

  const count = countRequests(page);
  await page.goto("/admin/risk-register");
  await expect(
    page.getByRole("heading", { name: `Risk Register for ${A.name}` }),
  ).toBeVisible({ timeout: 60_000 });
  const regenerate = page.getByRole("button", { name: "Regenerate" });
  await expect(regenerate).toBeVisible({ timeout: 60_000 });
  // Generate's `disabled` also ORs work in flight, a catalog mismatch, a
  // duplicate service and an unreadable AI status. None is set for this tenant
  // (one service per kind, the seeded catalog, a readable status), so it must
  // be ENABLED here, or "disabled after Apply" below would prove nothing.
  await expect(regenerate).toBeEnabled();

  const listsBefore = count("/api/proxy/admin/clients");
  const cookieReadsBefore = count("/api/active-client");
  const mountBefore = await mountedAt(page);
  expect(mountBefore).toBeTruthy();

  // --- The lock, for real: hold the page load Apply starts. -----------------
  let held: Route | null = null;
  const isBLoad = (url: URL) =>
    url.pathname === "/admin/risk-register" &&
    url.searchParams.get("client") === B.id;
  await page.route(isBLoad, async (route) => {
    if (route.request().resourceType() === "document") held = route;
    else await route.continue();
  });
  await page
    .getByRole("combobox", { name: "Client for this page" })
    .selectOption(B.id);
  await page.getByRole("button", { name: "Show this client" }).click();
  await expect.poll(() => held !== null, { timeout: 30_000 }).toBe(true);
  await expect(regenerate).toBeDisabled();
  await expect(page.getByText(string18(B.name))).toBeVisible();
  await expect(
    page.getByRole("heading", { name: `Risk Register for ${A.name}` }),
  ).toBeVisible();
  await (held as unknown as Route).continue();
  await page.unroute(isBLoad);

  // --- After Apply: the URL, a fresh mount, B's page, the cookie still A. ---
  await expect.poll(() => urlClient(page), { timeout: 60_000 }).toBe(B.id);
  await expect(
    page.getByRole("heading", { name: `Risk Register for ${B.name}` }),
  ).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Regenerate" })).toBeEnabled({
    timeout: 60_000,
  });
  // A soft navigation would keep the mount, and its marker. The read counts
  // only show the new mount read something: the dev server's StrictMode runs
  // mount effects twice, so no exact number is asserted.
  expect(await mountedAt(page)).not.toBe(mountBefore);
  expect(count("/api/proxy/admin/clients")).toBeGreaterThan(listsBefore);
  expect(count("/api/active-client")).toBeGreaterThan(cookieReadsBefore);
  expect(await cookieClient(page)).toBe(A.id);

  // --- The Risk Register download is B's, with the cookie still on A. -------
  const rrDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: /^XLSX/ }).click();
  expect((await rrDownload).suggestedFilename()).toMatch(
    new RegExp(`^${B.name}_`),
  );
  expect(await cookieClient(page)).toBe(A.id);

  // --- A reload keeps B. -----------------------------------------------------
  const gatesBefore = count(`/api/proxy/risk/clients/${B.id}/gate`);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: `Risk Register for ${B.name}` }),
  ).toBeVisible({ timeout: 60_000 });
  await expect
    .poll(() => count(`/api/proxy/risk/clients/${B.id}/gate`), {
      timeout: 30_000,
    })
    .toBeGreaterThan(gatesBefore);
  expect(await cookieClient(page)).toBe(A.id);

  // --- The sidebar's move to Deliverables keeps B. --------------------------
  await page
    .getByRole("navigation", { name: "Primary" })
    .first()
    .getByRole("link", { name: "Deliverables", exact: true })
    .click();
  await expect
    .poll(() => new URL(page.url()).pathname, { timeout: 60_000 })
    .toBe("/admin/deliverables");
  await expect.poll(() => urlClient(page), { timeout: 30_000 }).toBe(B.id);
  await expect(
    page.getByRole("heading", { name: `Deliverables for ${B.name}` }),
  ).toBeVisible({ timeout: 60_000 });
  const delDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "PDF", exact: true }).first().click();
  expect((await delDownload).suggestedFilename()).toMatch(
    new RegExp(`^${B.name}_`),
  );
  expect(await cookieClient(page)).toBe(A.id);
});

test("behind the archive dialog the picker is inert, so Apply cannot switch the client mid-archive", async ({
  page,
  request,
}) => {
  test.slow();
  const token = await adminApiToken(request);
  const A = await createTenant(request, token, "RRTwoInertA");
  const B = await createTenant(request, token, "RRTwoInertB");
  // 1. Two CISA ZT services raise the duplicate banner and its archive buttons.
  const hA = headers(token, A.id);
  await openService(
    request,
    hA,
    "attack",
    "attack_coverage",
    `${A.name} ATT&CK`,
  );
  await openService(request, hA, "zt", "zero_trust_cisa", `${A.name} ZT One`);
  await openService(request, hA, "zt", "zero_trust_cisa", `${A.name} ZT Two`);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await setCookieClient(page, A.id);
  await page.goto("/admin/risk-register");
  await expect(
    page.getByRole("heading", { name: `Risk Register for ${A.name}` }),
  ).toBeVisible({ timeout: 60_000 });

  // Counted from here: B's gate request, the one a switch would make.
  const count = countRequests(page);
  const bGate = `/api/proxy/risk/clients/${B.id}/gate`;

  // 2. Choose B BEFORE opening the dialog. From here only inertness stops Apply.
  const picker = page.getByRole("combobox", { name: "Client for this page" });
  const apply = page.getByRole("button", { name: "Show this client" });
  await picker.selectOption(B.id);
  await expect(apply).toBeEnabled();

  // 3. Hold the archive POST, open the dialog and confirm.
  let held: Route | null = null;
  await page.route(
    "**/api/proxy/risk/clients/*/services/*/archive",
    (route) => {
      held = route;
    },
  );
  await page.getByRole("button", { name: `Archive ${A.name} ZT Two` }).click();
  const dialog = page.getByRole("dialog", {
    name: `Archive ${A.name} ZT Two?`,
  });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Yes, archive" }).click();
  await expect.poll(() => held !== null, { timeout: 30_000 }).toBe(true);

  // 4. Apply's box, read immediately before the click.
  const box = await apply.boundingBox();
  expect(box, "Apply has a box").not.toBeNull();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  const viewport = page.viewportSize()!;
  expect(x > 0 && y > 0 && x < viewport.width && y < viewport.height).toBe(
    true,
  );

  // 5. What is under the point: the modal's backdrop, i.e. the <dialog>. Soft,
  // so a revert still runs step 7, which must go red on its own.
  expect
    .soft(
      await page.evaluate(
        ([px, py]) => document.elementFromPoint(px, py)?.tagName,
        [x, y],
      ),
    )
    .toBe("DIALOG");

  // 6. A real click at that point: `locator.click()` would wait out its
  // timeout behind a modal, and `dispatchEvent` ignores `inert`.
  await page.mouse.click(x, y);

  // 7. Wait out the window a switch would need, then assert.
  const navigated = await page
    .waitForURL((u) => u.searchParams.get("client") === B.id, {
      timeout: SWITCH_WINDOW_MS,
    })
    .then(
      () => true,
      () => false,
    );
  const gateSeen = await expect
    .poll(() => count(bGate), { timeout: SWITCH_WINDOW_MS })
    .toBeGreaterThan(0)
    .then(
      () => true,
      () => false,
    );
  expect
    .soft(navigated, "a click behind the modal switched client")
    .toBe(false);
  await expect
    .soft(page.getByRole("heading", { level: 1 }))
    .toHaveText(`Risk Register for ${A.name}`);
  expect.soft(urlClient(page)).not.toBe(B.id);
  // Only this one pins inertness itself; the rest pin its consequence.
  await picker.focus();
  await expect.soft(picker).not.toBeFocused();
  expect.soft(gateSeen, "B's gate was requested").toBe(false);

  // 8. Release the archive with a 2xx, then Apply for real: B within the same
  // window. This calibrates step 7: too short a window turns THIS red.
  await (held as unknown as Route).fulfill({ status: 204 });
  await expect(dialog).toBeHidden({ timeout: 30_000 });
  await apply.click();
  await page.waitForURL((u) => u.searchParams.get("client") === B.id, {
    timeout: SWITCH_WINDOW_MS,
  });
  await expect
    .poll(() => count(bGate), { timeout: SWITCH_WINDOW_MS })
    .toBeGreaterThan(0);
  await expect(
    page.getByRole("heading", { name: `Risk Register for ${B.name}` }),
  ).toBeVisible();
});
