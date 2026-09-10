/**
 * Can ONE continuously-used admin session last longer than a take?
 *
 * ## What this measures, and what it deliberately does not
 *
 * It measures exactly one thing: **drive a single admin session continuously
 * for N minutes and record whether it ever stops being authenticated.** That
 * is the question the chapter plan turns on — the script budgets ~34 minutes
 * and the 2026-09-10 engagement run took a terminal 401 at ~14.7.
 *
 * It does NOT compare "UI navigation" against "API calls". **A previous
 * version of this file did, and it was unsound twice over. Both faults are
 * recorded here because the second is the kind that produces a confident wrong
 * answer:**
 *
 *  1. **The premise was false.** Every `apps/web/src/app/api/proxy/**` handler
 *     opens `const session = await auth();`, and `auth()`'s `jwt` callback in
 *     `lib/auth/options.ts` ends `return refreshAccessToken(token)` once the
 *     access token is inside `REFRESH_SKEW_MS` of expiry. So a
 *     `page.request` against the proxy runs the SAME refresh path as a page
 *     render. The two "arms" never differed on the variable they named.
 *
 *  2. **The arms were not independent.** Both signed in as `ADMIN_EMAIL`, and
 *     `apps/api/app/routes/auth.py` keeps ONE refresh jti per USER
 *     (`user.active_refresh_jti`, with `previous_refresh_jti` honoured only
 *     inside `jwt_refresh_grace_seconds`, default 60). The second sign-in
 *     therefore invalidated the first arm on the spot, and the probe would
 *     have printed "UI arm died, API arm SURVIVED" — determined entirely by
 *     sign-in ORDER, and the exact inverse of a real finding.
 *
 * So: one account, one session, one signal. Mixed UI and API traffic, because
 * a real take is mixed and because they are not separable anyway.
 *
 * ## Reading it
 *
 * An OBSERVATION instrument. It prints a timeline and asserts nothing about
 * the product, but DOES fail if it cannot establish a session at the start —
 * a probe that never authenticated measures nothing.
 *
 * `died at t+X` is the answer. `SURVIVED` is also an answer, and it means the
 * engagement run's 401 has a cause other than elapsed time — most likely the
 * rotated refresh token not reaching the session cookie, which would make the
 * trigger a particular REQUEST rather than a duration.
 *
 * **Avoids `/admin/risk-register` deliberately** — dev sits at migration 0046
 * without `risk_registers.provenance`, so any Risk surface 500s once #275
 * merges. See the ACTIVE HOLD in `kentro-demo-failed-items.md`.
 *
 *     SHIELD_SESSION_PROBE=1 npx playwright test engagement/session-longevity.spec.ts
 */
import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

test.skip(
  process.env.SHIELD_SESSION_PROBE !== "1",
  "Session-longevity probe; set SHIELD_SESSION_PROBE=1. Excluded from CI's bare `npx playwright test`.",
);

/**
 * Longer than the take it is clearing. The chapter script budgets ~34 minutes;
 * 25 crosses the observed ~14.7-minute failure with room either side, and a
 * window shorter than the thing being measured reports "survived" for the
 * least interesting reason.
 */
const WINDOW_MIN = Number(process.env.SHIELD_SESSION_PROBE_MINUTES ?? "25");
const PROBE_EVERY_MS = 30_000;

/** Cheap, already warmed, all behind auth, and none of them Risk. */
const UI_ROUTES = [
  "/admin/queue",
  "/admin/deliverables",
  "/admin/audit",
  "/admin/health",
];

test("how long one continuously-used admin session lasts", async ({ page }) => {
  test.setTimeout((WINDOW_MIN + 10) * 60_000);

  try {
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  } catch (err) {
    // `signIn`'s own comments describe a race where `waitForURL` gives up after
    // the navigation has already landed. Verify the state rather than trust the
    // throw — observed on this stack 2026-09-10.
    console.log(`session-probe: signIn threw (${String(err).slice(0, 70)}…)`);
  }
  await page.goto("/admin/queue");
  await expect(
    page.getByRole("button", { name: "Sign out" }),
    "never established a session, so this probe measures nothing",
  ).toBeVisible({ timeout: 60_000 });

  const t0 = Date.now();
  const mins = () => ((Date.now() - t0) / 60_000).toFixed(1);
  console.log(
    `session-probe: signed in; window ${WINDOW_MIN} min, probe every ${PROBE_EVERY_MS / 1000}s`,
  );

  let firstFailureAt: string | null = null;
  let firstFailureWhat = "";
  let recovered = false;
  let probes = 0;
  let alive = 0;

  for (let i = 0; Date.now() - t0 < WINDOW_MIN * 60_000; i++) {
    const at = mins();
    let okThisRound = true;
    const detail: string[] = [];

    // UI navigation. A bounce to /sign-in is the authoritative "gone" signal:
    // the page renders fine, it is simply not the page that was asked for.
    try {
      const route = UI_ROUTES[i % UI_ROUTES.length];
      await page.goto(route, { timeout: 60_000 });
      const path = new URL(page.url()).pathname;
      if (path.startsWith("/sign-in")) {
        okThisRound = false;
        detail.push(`ui BOUNCED to ${path}`);
      } else {
        detail.push(`ui ${route}`);
      }
    } catch (err) {
      okThisRound = false;
      detail.push(`ui threw ${String(err).slice(0, 50)}`);
    }

    // An API call through the same session, because a take is mixed traffic.
    try {
      const res = await page.request.get("/api/proxy/admin/ai-status");
      detail.push(`api ${res.status()}`);
      if (!res.ok()) okThisRound = false;
    } catch (err) {
      okThisRound = false;
      detail.push(`api threw ${String(err).slice(0, 50)}`);
    }

    probes++;
    if (okThisRound) {
      alive++;
      // Recovery is worth knowing: a session that fails once and comes back is
      // a rotation race, and one that never returns is a terminal
      // invalidation. The engagement run showed the terminal kind.
      if (firstFailureAt !== null) recovered = true;
    } else if (firstFailureAt === null) {
      firstFailureAt = at;
      firstFailureWhat = detail.join(", ");
    }

    console.log(
      `session-probe: t+${at}m ${okThisRound ? "alive" : "DEAD"} — ${detail.join(", ")}`,
    );

    const spent = Date.now() - t0;
    const nextAt = (i + 1) * PROBE_EVERY_MS;
    if (nextAt > spent) await page.waitForTimeout(nextAt - spent);
  }

  console.log(
    `\nsession-probe: RESULT over ${mins()} minutes, ${alive}/${probes} probes authenticated\n` +
      (firstFailureAt === null
        ? `  SURVIVED — one session, driven continuously, never lost auth.\n` +
          `  So the engagement run's terminal 401 is NOT explained by elapsed\n` +
          `  time alone, and the next suspect is the refresh rotation not\n` +
          `  reaching the session cookie (a REQUEST-triggered failure).`
        : `  FIRST FAILURE at t+${firstFailureAt}m — ${firstFailureWhat}\n` +
          `  Recovered afterwards: ${recovered ? "YES (a rotation race)" : "NO (terminal, as the engagement run saw)"}`) +
      `\n  Read JWT_ACCESS_TTL_SECONDS from the RUNNING container before\n` +
      `  interpreting this — it is 900 in this stack's .env while config.py\n` +
      `  defaults to 3600, so neither file is authoritative on its own.`,
  );
});
