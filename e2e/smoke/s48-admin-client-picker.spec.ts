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
/**
 * Step 7's NEGATIVE window: how long it waits for a switch that must not
 * happen. It is not a guess: step 8, on the same run, times a real switch and
 * requires it to fit inside this window, so a switch the blocked click had
 * caused could not have been too slow to see.
 */
const NEGATIVE_WINDOW_MS = 20_000;
/**
 * A POSITIVE wait for a full page load on the dev server, the same order as
 * this file's other first-load waits: Apply is a `location.replace`, so the
 * new document is server-rendered and its scripts reloaded, which takes
 * seconds on a CI runner. A 3 s positive window here was miscalibrated.
 */
const FIRST_LOAD_MS = 60_000;
/**
 * EVERY wait in this file is bounded, well under the test timeout (about 15
 * minutes under `test.slow`): the config sets no action or navigation timeout,
 * so an unbounded wait that cannot resolve eats the whole test and its retry
 * instead of failing and naming its step. #1140's E2E job ran into the job
 * limit that way. STEP_MS for an action on a page already loaded, LOAD_MS for
 * a page or a download the dev server may compile cold.
 */
const STEP_MS = 30_000;
const LOAD_MS = 60_000;
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
    { timeout: LOAD_MS * 2 },
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
    timeout: STEP_MS,
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
    .getAttribute("data-mounted-at", { timeout: STEP_MS });
}

test("the picker's client, not the cookie's, reaches the URL, a reload, the twin page and both downloads", async ({
  page,
  request,
}) => {
  test.slow();
  const { A, B } =
    await test.step("1. two tenants, each with a register and a CSF deliverable", async () => {
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
      return { A, B };
    });

  const count = countRequests(page);
  const regenerate = page.getByRole("button", { name: "Regenerate" });
  const { listsBefore, cookieReadsBefore, mountBefore } =
    await test.step("2. the page opens on the cookie's client, A", async () => {
      await page.goto("/admin/risk-register", { timeout: LOAD_MS });
      await expect(
        page.getByRole("heading", { name: `Risk Register for ${A.name}` }),
      ).toBeVisible({ timeout: LOAD_MS });
      await expect(regenerate).toBeVisible({ timeout: LOAD_MS });
      // Generate's `disabled` also ORs work in flight, a catalog mismatch, a
      // duplicate service and an unreadable AI status. None is set for this
      // tenant, so it must be ENABLED here, or "disabled after Apply" below
      // would prove nothing.
      await expect(regenerate).toBeEnabled({ timeout: STEP_MS });
      const mountBefore = await mountedAt(page);
      expect(mountBefore).toBeTruthy();
      return {
        listsBefore: count("/api/proxy/admin/clients"),
        cookieReadsBefore: count("/api/active-client"),
        mountBefore,
      };
    });

  await test.step("3. Apply locks the page while its load is held", async () => {
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
      .selectOption(B.id, { timeout: STEP_MS });
    await page
      .getByRole("button", { name: "Show this client" })
      .click({ timeout: STEP_MS });
    await expect.poll(() => held !== null, { timeout: STEP_MS }).toBe(true);
    await expect(regenerate).toBeDisabled({ timeout: STEP_MS });
    await expect(page.getByText(string18(B.name))).toBeVisible({
      timeout: STEP_MS,
    });
    await expect(
      page.getByRole("heading", { name: `Risk Register for ${A.name}` }),
    ).toBeVisible({ timeout: STEP_MS });
    await (held as unknown as Route).continue();
    await page.unroute(isBLoad);
  });

  await test.step("4. after Apply: B's page, a fresh mount, the cookie still A", async () => {
    await expect.poll(() => urlClient(page), { timeout: LOAD_MS }).toBe(B.id);
    await expect(
      page.getByRole("heading", { name: `Risk Register for ${B.name}` }),
    ).toBeVisible({ timeout: LOAD_MS });
    await expect(regenerate).toBeEnabled({ timeout: LOAD_MS });
    // A soft navigation would keep the mount, and its marker. The read counts
    // only show the new mount read something: the dev server's StrictMode runs
    // mount effects twice, so no exact number is asserted.
    expect(await mountedAt(page)).not.toBe(mountBefore);
    expect(count("/api/proxy/admin/clients")).toBeGreaterThan(listsBefore);
    expect(count("/api/active-client")).toBeGreaterThan(cookieReadsBefore);
    expect(await cookieClient(page)).toBe(A.id);
  });

  await test.step("5. the Risk Register download is B's", async () => {
    const rrDownload = page.waitForEvent("download", { timeout: LOAD_MS });
    await page.getByRole("link", { name: /^XLSX/ }).click({ timeout: STEP_MS });
    expect((await rrDownload).suggestedFilename()).toMatch(
      new RegExp(`^${B.name}_`),
    );
    expect(await cookieClient(page)).toBe(A.id);
  });

  await test.step("6. a reload keeps B", async () => {
    const gatesBefore = count(`/api/proxy/risk/clients/${B.id}/gate`);
    await page.reload({ timeout: LOAD_MS });
    await expect(
      page.getByRole("heading", { name: `Risk Register for ${B.name}` }),
    ).toBeVisible({ timeout: LOAD_MS });
    await expect
      .poll(() => count(`/api/proxy/risk/clients/${B.id}/gate`), {
        timeout: STEP_MS,
      })
      .toBeGreaterThan(gatesBefore);
    expect(await cookieClient(page)).toBe(A.id);
  });

  await test.step("7. the sidebar's move to Deliverables keeps B, and its download is B's", async () => {
    await page
      .getByRole("navigation", { name: "Primary" })
      .first()
      .getByRole("link", { name: "Deliverables", exact: true })
      .click({ timeout: STEP_MS });
    await expect
      .poll(() => new URL(page.url()).pathname, { timeout: LOAD_MS })
      .toBe("/admin/deliverables");
    await expect.poll(() => urlClient(page), { timeout: STEP_MS }).toBe(B.id);
    await expect(
      page.getByRole("heading", { name: `Deliverables for ${B.name}` }),
    ).toBeVisible({ timeout: LOAD_MS });
    const delDownload = page.waitForEvent("download", { timeout: LOAD_MS });
    await page
      .getByRole("link", { name: "PDF", exact: true })
      .first()
      .click({ timeout: STEP_MS });
    expect((await delDownload).suggestedFilename()).toMatch(
      new RegExp(`^${B.name}_`),
    );
    expect(await cookieClient(page)).toBe(A.id);
  });
});

test("behind the archive dialog the picker is inert, so Apply cannot switch the client mid-archive", async ({
  page,
  request,
}) => {
  test.slow();
  // The picker and Apply are located by CSS, never by role, throughout this
  // test. While the modal is open they are inert, and whether a role query
  // still finds an inert element is a property of the accessibility tree, not
  // of this page; a role locator that stopped resolving would turn every
  // action on it into a wait for the test timeout (#1140's hang). CSS
  // resolves them whether or not they are inert.
  const picker = page.locator('select[aria-label="Client for this page"]');
  const apply = page.locator("button", { hasText: "Show this client" });
  const h1 = page.locator("h1");

  const { A, B } =
    await test.step("1. tenant A has two CISA ZT services, so the duplicate banner shows", async () => {
      const token = await adminApiToken(request);
      const A = await createTenant(request, token, "RRTwoInertA");
      const B = await createTenant(request, token, "RRTwoInertB");
      const hA = headers(token, A.id);
      await openService(
        request,
        hA,
        "attack",
        "attack_coverage",
        `${A.name} ATT&CK`,
      );
      await openService(
        request,
        hA,
        "zt",
        "zero_trust_cisa",
        `${A.name} ZT One`,
      );
      await openService(
        request,
        hA,
        "zt",
        "zero_trust_cisa",
        `${A.name} ZT Two`,
      );
      await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
      await setCookieClient(page, A.id);
      await page.goto("/admin/risk-register", { timeout: LOAD_MS });
      await expect(h1).toHaveText(`Risk Register for ${A.name}`, {
        timeout: LOAD_MS,
      });
      return { A, B };
    });

  // Counted from here: B's gate request, the one a switch would make.
  const count = countRequests(page);
  const bGate = `/api/proxy/risk/clients/${B.id}/gate`;

  // Apply is found and measured while it is still interactive, before the
  // dialog; step 4 re-reads its point immediately before the click.
  await test.step("2. choose B before the dialog, and find Apply", async () => {
    await picker.selectOption(B.id, { timeout: STEP_MS });
    await expect(apply).toBeEnabled({ timeout: STEP_MS });
    const box = await apply.boundingBox({ timeout: STEP_MS });
    expect(box, "Apply has a box").not.toBeNull();
  });

  let held: Route | null = null;
  const dialog = page.getByRole("dialog", {
    name: `Archive ${A.name} ZT Two?`,
  });
  await test.step("3. hold the archive POST, open the dialog and confirm", async () => {
    await page.route(
      "**/api/proxy/risk/clients/*/services/*/archive",
      (route) => {
        held = route;
      },
    );
    await page
      .getByRole("button", { name: `Archive ${A.name} ZT Two` })
      .click({ timeout: STEP_MS });
    await expect(dialog).toBeVisible({ timeout: STEP_MS });
    await dialog
      .getByRole("button", { name: "Yes, archive" })
      .click({ timeout: STEP_MS });
    await expect.poll(() => held !== null, { timeout: STEP_MS }).toBe(true);
  });

  // 4. Apply's point, read immediately before the click (by CSS, so it
  // resolves while Apply is inert).
  const { x, y } =
    await test.step("4. Apply's point, read immediately before the click", async () => {
      const box = await apply.boundingBox({ timeout: STEP_MS });
      expect(box, "Apply has a box").not.toBeNull();
      const x = box!.x + box!.width / 2;
      const y = box!.y + box!.height / 2;
      const viewport = page.viewportSize()!;
      expect(x > 0 && y > 0 && x < viewport.width && y < viewport.height).toBe(
        true,
      );
      return { x, y };
    });

  await test.step("5. the point over Apply is covered by the open modal", async () => {
    // Over the backdrop the hit is the <dialog> itself; over the panel it is
    // a CHILD of it, so the check is `closest("dialog")`, not the tag name.
    // Soft, so a revert still runs step 7, which must go red on its own.
    expect
      .soft(
        await page.evaluate(
          ([px, py]) => {
            const hit = document.elementFromPoint(px, py);
            const modal = hit?.closest("dialog");
            return modal instanceof HTMLDialogElement && modal.open;
          },
          [x, y],
        ),
        "the point over Apply is covered by the open modal",
      )
      .toBe(true);
  });

  await test.step("6. a real click at Apply's point", async () => {
    // `locator.click()` would wait behind a modal, and `dispatchEvent`
    // ignores `inert`.
    await page.mouse.click(x, y);
  });

  await test.step("7. no switch happened", async () => {
    // `commit` is the earliest point a navigation is visible, and the point
    // step 8 times, so the two measure the same thing. A switch caused by
    // this click commits well inside the window (step 8 proves a real one
    // does, on this run), so if the modal did not block it, `navigated` is
    // true and this goes red.
    const navigated = await page
      .waitForURL((u) => u.searchParams.get("client") === B.id, {
        timeout: NEGATIVE_WINDOW_MS,
        waitUntil: "commit",
      })
      .then(
        () => true,
        () => false,
      );
    const gateSeen = await expect
      .poll(() => count(bGate), { timeout: NEGATIVE_WINDOW_MS })
      .toBeGreaterThan(0)
      .then(
        () => true,
        () => false,
      );
    expect
      .soft(navigated, "a click behind the modal switched client")
      .toBe(false);
    await expect
      .soft(h1)
      .toHaveText(`Risk Register for ${A.name}`, { timeout: STEP_MS });
    expect.soft(urlClient(page)).not.toBe(B.id);
    // Only this one pins inertness itself; the rest pin its consequence. Read
    // in the page, so nothing waits on the element being actionable.
    expect
      .soft(
        await picker.evaluate(
          (el) => {
            (el as HTMLElement).focus();
            return document.activeElement === el;
          },
          undefined,
          { timeout: STEP_MS },
        ),
        "the picker took focus behind the modal",
      )
      .toBe(false);
    expect.soft(gateSeen, "B's gate was requested").toBe(false);
  });

  await test.step("8. release the archive, then Apply for real, timed", async () => {
    // The waits are POSITIVE, so they get a full page load's time
    // (FIRST_LOAD_MS). What a real switch TOOK is measured and must fit inside
    // step 7's windows: that is what makes step 7's "nothing happened" mean
    // something. If CI ever switches slower than the window, THIS goes red and
    // says so, rather than step 7 passing over a switch it was too impatient
    // to see.
    await (held as unknown as Route).fulfill({ status: 204 });
    await expect(dialog).toBeHidden({ timeout: STEP_MS });
    // Timed from the click itself, not from the wait for Apply to be enabled.
    await expect(apply).toBeEnabled({ timeout: STEP_MS });
    const clickedAt = Date.now();
    await apply.click({ timeout: STEP_MS });
    await page.waitForURL((u) => u.searchParams.get("client") === B.id, {
      timeout: FIRST_LOAD_MS,
      waitUntil: "commit",
    });
    const committedMs = Date.now() - clickedAt;
    await expect
      .poll(() => count(bGate), { timeout: FIRST_LOAD_MS })
      .toBeGreaterThan(0);
    const gateMs = Date.now() - clickedAt;
    // Step 7 waited NEGATIVE_WINDOW_MS for the commit, and then another
    // NEGATIVE_WINDOW_MS for the gate request, so the gate's bound is twice it.
    expect(
      committedMs,
      `a real switch committed in ${committedMs} ms; step 7's window is ${NEGATIVE_WINDOW_MS} ms`,
    ).toBeLessThan(NEGATIVE_WINDOW_MS);
    expect(
      gateMs,
      `a real switch requested B's gate in ${gateMs} ms; step 7 watched for ${2 * NEGATIVE_WINDOW_MS} ms`,
    ).toBeLessThan(2 * NEGATIVE_WINDOW_MS);
    await expect(h1).toHaveText(`Risk Register for ${B.name}`, {
      timeout: FIRST_LOAD_MS,
    });
  });
});
