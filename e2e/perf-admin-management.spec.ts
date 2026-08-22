/**
 * #111 measurement — NOT part of the smoke suite.
 *
 * `/admin/management` renders one card per client, and each card fires its own
 * `listClientUsers()` and `listDomains()` from a mount `useEffect`
 * (`ManagementView.tsx`). So the page costs **1 + 2N** requests, where N is the
 * number of non-archived clients.
 *
 * `s2-management` and `s33-admin-remove:84` both hang in `settleForHydration`,
 * which waits on `networkidle` — 500ms with no in-flight request. With a large N
 * that condition is reached late or not at all inside the test budget.
 *
 * CI never sees this: its runners start with empty volumes, so N is single
 * digits. This spec exists to turn "probably drift" into a number, and to be
 * re-run against a freshly seeded database for the comparison.
 *
 * OPT-IN. `playwright.config.ts` sets `testDir: "."`, so this file IS collected
 * by a bare `npx playwright test` -- including CI's. It is gated behind
 * `E2E_PERF=1`, the same pattern `s26-oidc-login` uses for `E2E_OIDC`, so the
 * smoke suite is unchanged and CI does not spend two minutes measuring a number
 * its own empty-volume runners can never reproduce.
 *
 * Run explicitly:
 *   E2E_PERF=1 npx playwright test perf-admin-management.spec.ts
 */
import { expect, test } from "@playwright/test";

const PERF = process.env.E2E_PERF === "1";

const ADMIN_EMAIL = "admin@kentro.example";
const ADMIN_PASSWORD = "DemoPass!2026";

test("measure: /admin/management request fan-out and time to networkidle", async ({
  page,
}) => {
  test.skip(!PERF, "measurement only — set E2E_PERF=1 to run");
  test.setTimeout(600_000);

  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/admin/, { timeout: 60_000 });

  let apiCalls = 0;
  let userCalls = 0;
  let domainCalls = 0;
  page.on("request", (r) => {
    const u = r.url();
    if (!u.includes("/api/proxy/")) return;
    apiCalls += 1;
    if (u.includes("/users")) userCalls += 1;
    if (u.includes("/domains")) domainCalls += 1;
  });

  const t0 = Date.now();
  await page.goto("/admin/management");
  const tNav = Date.now() - t0;

  let idleMs = -1;
  try {
    await page.waitForLoadState("networkidle", { timeout: 300_000 });
    idleMs = Date.now() - t0;
  } catch {
    idleMs = -1; // never settled inside 300s
  }

  const cards = await page.getByRole("heading", { level: 3 }).count();

  console.log("=== #111 measurement ===");
  console.log(`client cards rendered : ${cards}`);
  console.log(`proxy requests        : ${apiCalls}`);
  console.log(`  …/users             : ${userCalls}`);
  console.log(`  …/domains           : ${domainCalls}`);
  console.log(`navigation resolved   : ${tNav} ms`);
  console.log(
    `networkidle reached   : ${idleMs === -1 ? "NEVER (>300s)" : idleMs + " ms"}`,
  );
  console.log(
    `settleForHydration budget: s2 = 90s, s33:84 = 240s (whole test, not just this)`,
  );

  // Not an assertion about correctness — the page must at least render.
  expect(cards).toBeGreaterThan(0);
});
