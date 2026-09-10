/**
 * Does an admin session survive longer than the access-token TTL, and does it
 * matter HOW the session is being used?
 *
 * ## The observation this exists to settle
 *
 * On the 2026-09-10 12:46 engagement run the ATT&CK scoring loop ran for
 * 402,780 ms of continuous `page.request.patch` calls and then took
 * `401 {"reason": ... "Not signed in."}`. It never recovered: every later phase
 * failed the same way and the next UI navigation bounced to `/sign-in`.
 *
 * `JWT_ACCESS_TTL_SECONDS=900`. Admin sign-in was ~08:50 and the first 401 was
 * ~09:04:45 — ≈14.7 minutes, consistent with the TTL to within the precision
 * available. But "consistent with" is not "caused by", and the failing calls
 * were all `page.request`, which may not exercise whatever refresh path normal
 * UI interaction triggers.
 *
 * **That distinction decides the demonstration.** If a human-driven session
 * refreshes and an API-only loop does not, this is an instrument problem and
 * the fix is in the spec. If both die at ~15 minutes, then NO TAKE LONGER THAN
 * 15 MINUTES CAN COMPLETE without re-authenticating on camera — and the
 * chapter script budgets ~34.
 *
 * ## Why two arms, concurrently
 *
 * One arm would confound the answer with machine load and wall-clock drift: a
 * session dying at minute 15 tells you nothing unless something else was alive
 * at minute 15 under the same conditions. So both arms run in the SAME test,
 * in SEPARATE browser contexts (separate cookie jars, therefore genuinely
 * independent sessions), signed in within seconds of each other:
 *
 *   * **UI arm** — `page.goto` between admin routes, which is what a presenter
 *     does.
 *   * **API arm** — `page.request.get` against an admin endpoint, which is what
 *     the engagement instrument does.
 *
 * Each arm records, per probe, whether it is still authenticated and at what
 * elapsed time. Whichever dies first — or neither — is the answer, and the
 * other arm is the control.
 *
 * ## Reading the result
 *
 * The arms are NOT a pass/fail. This is an observation instrument like
 * `full-engagement.spec.ts`: it prints a table and does not assert a verdict
 * about the product. It DOES fail if it cannot establish either arm at the
 * start, because an arm that never signed in measures nothing.
 *
 * Opt-in, like every other engagement spec — it costs 20+ minutes and must not
 * join CI's bare `npx playwright test`.
 *
 *     SHIELD_SESSION_PROBE=1 npx playwright test engagement/session-longevity.spec.ts
 */
import { expect, test } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

test.skip(
  process.env.SHIELD_SESSION_PROBE !== "1",
  "Session-longevity probe; set SHIELD_SESSION_PROBE=1. Excluded from CI's bare `npx playwright test`.",
);

/**
 * Long enough to cross a 900s access TTL with margin on both sides. Override
 * with SHIELD_SESSION_PROBE_MINUTES when the TTL under test is different --
 * a probe whose window is shorter than the thing it measures reports "survived"
 * for the least interesting reason.
 */
const WINDOW_MIN = Number(process.env.SHIELD_SESSION_PROBE_MINUTES ?? "20");
const PROBE_EVERY_MS = 30_000;

/** Admin routes to walk. Cheap, already warmed, and all behind auth. */
const UI_ROUTES = [
  "/admin/queue",
  "/admin/deliverables",
  "/admin/audit",
  "/admin/health",
];

interface Sample {
  minute: string;
  ok: boolean;
  detail: string;
}

async function newSignedInContext(
  browser: import("@playwright/test").Browser,
  label: string,
): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  try {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  } catch (err) {
    // `signIn`'s own comments describe a race where `waitForURL` gives up after
    // the navigation has already landed. Verify the state rather than trust
    // the throw -- observed on this stack 2026-09-10.
    console.log(`${label}: signIn threw (${String(err).slice(0, 70)}…)`);
  }
  await page.goto("/admin/queue");
  await expect(
    page.getByRole("button", { name: "Sign out" }),
    `${label}: never established a session, so this arm measures nothing`,
  ).toBeVisible({ timeout: 60_000 });
  return { ctx, page };
}

test("how long an admin session lasts, driven by UI versus by API", async ({
  browser,
}) => {
  test.setTimeout((WINDOW_MIN + 8) * 60_000);

  const ui = await newSignedInContext(browser, "ui-arm");
  const api = await newSignedInContext(browser, "api-arm");
  const t0 = Date.now();
  console.log(
    `session-probe: both arms signed in; window ${WINDOW_MIN} min, probe every ${PROBE_EVERY_MS / 1000}s`,
  );

  const uiSamples: Sample[] = [];
  const apiSamples: Sample[] = [];
  let uiDiedAt: string | null = null;
  let apiDiedAt: string | null = null;

  const mins = () => ((Date.now() - t0) / 60_000).toFixed(1);

  for (let i = 0; Date.now() - t0 < WINDOW_MIN * 60_000; i++) {
    const at = mins();

    // --- UI arm: a real navigation, as a presenter would drive it ----------
    try {
      const route = UI_ROUTES[i % UI_ROUTES.length];
      await ui.page.goto(route, { timeout: 60_000 });
      const path = new URL(ui.page.url()).pathname;
      // A bounce to /sign-in is the authoritative "session is gone" signal --
      // the page renders fine, it is simply not the page that was asked for.
      const alive = !path.startsWith("/sign-in");
      uiSamples.push({
        minute: at,
        ok: alive,
        detail: alive ? route : `BOUNCED to ${path}`,
      });
      if (!alive && uiDiedAt === null) uiDiedAt = at;
    } catch (err) {
      uiSamples.push({
        minute: at,
        ok: false,
        detail: String(err).slice(0, 60),
      });
      if (uiDiedAt === null) uiDiedAt = at;
    }

    // --- API arm: what the engagement instrument does ---------------------
    try {
      const res = await api.page.request.get("/api/proxy/admin/ai-status");
      const alive = res.ok();
      apiSamples.push({
        minute: at,
        ok: alive,
        detail: `HTTP ${res.status()}`,
      });
      if (!alive && apiDiedAt === null) apiDiedAt = at;
    } catch (err) {
      apiSamples.push({
        minute: at,
        ok: false,
        detail: String(err).slice(0, 60),
      });
      if (apiDiedAt === null) apiDiedAt = at;
    }

    const last = (s: Sample[]) => s[s.length - 1];
    console.log(
      `session-probe: t+${at}m  ui=${last(uiSamples).ok ? "alive" : "DEAD"} (${last(uiSamples).detail})  ` +
        `api=${last(apiSamples).ok ? "alive" : "DEAD"} (${last(apiSamples).detail})`,
    );

    const spent = Date.now() - t0;
    const nextAt = (i + 1) * PROBE_EVERY_MS;
    if (nextAt > spent) await ui.page.waitForTimeout(nextAt - spent);
  }

  console.log(
    `\nsession-probe: RESULT over ${mins()} minutes\n` +
      `  UI arm  : ${uiDiedAt ? `died at t+${uiDiedAt}m` : "SURVIVED"}  ` +
      `(${uiSamples.filter((s) => s.ok).length}/${uiSamples.length} probes alive)\n` +
      `  API arm : ${apiDiedAt ? `died at t+${apiDiedAt}m` : "SURVIVED"}  ` +
      `(${apiSamples.filter((s) => s.ok).length}/${apiSamples.length} probes alive)\n` +
      `  JWT_ACCESS_TTL_SECONDS is 900 (15.0 min) on this stack.\n` +
      `  Neither arm dying means the TTL is refreshed by BOTH paths and the\n` +
      `  engagement run's 401 has some other cause. Only the API arm dying\n` +
      `  means UI activity refreshes and the instrument's loop does not.`,
  );

  await ui.ctx.close();
  await api.ctx.close();
});
