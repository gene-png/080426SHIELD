import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * Warm every route the demonstration visits, and MEASURE what warming saved.
 *
 * ## Why this exists
 *
 * The stack runs `next dev`, not a production build. Measured against
 * `/sign-in` on 2026-09-09: first request 14.25s, second 0.69s, third 0.53s.
 * That first number is a cold webpack compile, and it is paid ONCE PER ROUTE,
 * on the first visit — which during a recorded take is a visible dead pause in
 * the middle of a sentence.
 *
 * Warming is the cheap half of the fix: visit every route once before the take,
 * so the recording only ever hits compiled routes. It changes nothing about
 * what is demonstrated, which is why it is preferred over switching to a
 * production build — that would be a stack configuration nothing in this repo
 * has been exercised against.
 *
 * ## Why it measures rather than just visiting
 *
 * A warm-up that silently failed to warm something is indistinguishable from
 * one that worked, and you would find out on camera. So each route is fetched
 * TWICE and both timings are recorded. The second timing is the one that
 * matters: if a route is still slow on its second visit, warming did not help
 * it and the cause is something other than compilation — that route needs a
 * different answer (a pre-seeded fixture, or a chapter re-order), and this
 * report is where that gets noticed.
 *
 * The report is written to `e2e/artifacts/warm-routes-<stamp>/` and is also
 * the raw material for the chapter script's per-chapter duration estimates.
 *
 * ## Dynamic segments
 *
 * Next compiles per ROUTE PATTERN, not per parameter value, so visiting
 * `/admin/services/<one id>/csf` warms `/admin/services/[id]/csf` for every
 * other id. The ids below come from the seeded Atlas client; if the database
 * has been wiped and reseeded they will differ, so they are read from the
 * environment when provided and fall back to a discovery pass through the UI.
 */

test.skip(
  process.env.SHIELD_WARM_ROUTES !== "1",
  "Route warm-up for the demonstration; set SHIELD_WARM_ROUTES=1. Excluded from CI's bare `npx playwright test`.",
);

test.use({ viewport: { width: 1920, height: 1080 } });

const STAMP = new Date()
  .toISOString()
  .replace(/[:.]/g, "-")
  .replace(/T/, "T")
  .slice(0, 19);

const OUT_DIR = path.resolve(
  __dirname,
  "..",
  "artifacts",
  `warm-routes-${STAMP}`,
);

/** Generous: a cold compile of a heavy dashboard route can genuinely take this long. */
const ROUTE_TIMEOUT_MS = 120_000;

interface Timing {
  route: string;
  group: string;
  cold: number | null;
  warm: number | null;
  note: string;
}

const timings: Timing[] = [];

/**
 * Visit twice and record both.
 *
 * Deliberately does NOT assert the page rendered correctly — this is a warm-up,
 * not a smoke test, and a route that 404s for a missing fixture still needs its
 * code compiled. A non-OK response is RECORDED rather than thrown, because a
 * warm-up that aborts halfway leaves the remaining routes cold and that is the
 * failure this file exists to prevent. The note column carries what happened.
 */
async function warm(page: Page, route: string, group: string): Promise<void> {
  let cold: number | null = null;
  let warm_: number | null = null;
  let note = "";
  for (const pass of [0, 1]) {
    const t0 = Date.now();
    try {
      const res = await page.goto(route, {
        timeout: ROUTE_TIMEOUT_MS,
        waitUntil: "domcontentloaded",
      });
      const ms = Date.now() - t0;
      if (pass === 0) cold = ms;
      else warm_ = ms;
      const status = res?.status();
      if (status !== undefined && status >= 400 && note === "") {
        note = `HTTP ${status}`;
      }
    } catch (err) {
      const ms = Date.now() - t0;
      if (pass === 0) cold = ms;
      else warm_ = ms;
      note = `FAILED: ${String(err).split("\n")[0].slice(0, 120)}`;
    }
  }
  timings.push({ route, group, cold, warm: warm_, note });
  // eslint-disable-next-line no-console
  console.log(
    `warm: ${route.padEnd(46)} cold=${String(cold).padStart(6)}ms warm=${String(warm_).padStart(6)}ms ${note}`,
  );
}

test("warm every demonstration route and measure the saving", async ({
  page,
}) => {
  test.setTimeout(30 * 60_000);

  // ---------------------------------------------------------------------
  // Unauthenticated routes first — they need no session, and warming
  // /sign-in before signing in means the sign-in step itself is not the
  // thing paying the 14s compile.
  // ---------------------------------------------------------------------
  for (const r of [
    "/sign-in",
    "/sign-up",
    "/forgot-password",
    "/help",
    "/accessibility",
    "/privacy",
    "/security",
  ]) {
    await warm(page, r, "public");
  }

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  // ---------------------------------------------------------------------
  // Service ids. Read from the environment when supplied; otherwise
  // discovered from the admin UI, because hardcoding ids that a
  // `docker compose down -v` invalidates is a warm-up that silently warms
  // a 404 route and reports success.
  // ---------------------------------------------------------------------
  const idFor: Record<string, string> = {};
  const wanted: Array<[string, string]> = [
    ["TECH_DEBT", "tech-debt"],
    ["NIST_CSF", "csf"],
    ["ZERO_TRUST_CISA", "zero-trust-cisa"],
    ["ZERO_TRUST_DOD", "zero-trust-dod"],
    ["ATTACK_COVERAGE", "attack-coverage"],
  ];

  const fromEnv = process.env.SHIELD_WARM_SERVICE_IDS;
  if (fromEnv) {
    // Format: KIND=uuid,KIND=uuid
    for (const pair of fromEnv.split(",")) {
      const [k, v] = pair.split("=");
      if (k && v) idFor[k.trim()] = v.trim();
    }
  }

  if (Object.keys(idFor).length === 0) {
    // Discover through the API the app itself uses, via the signed-in context
    // so the session cookie applies. Failure here is recorded and does not
    // abort: the non-service routes are still worth warming.
    try {
      const res = await page.request.get("/api/proxy/services");
      if (res.ok()) {
        const body = (await res.json()) as unknown;
        const rows = Array.isArray(body)
          ? body
          : ((body as { items?: unknown[] }).items ?? []);
        for (const row of rows as Array<Record<string, unknown>>) {
          const kind = String(row.kind ?? "");
          const id = String(row.id ?? "");
          if (kind && id && !(kind in idFor)) idFor[kind] = id;
        }
      }
    } catch {
      // recorded below by the absence of service rows in the report
    }
  }

  // ---------------------------------------------------------------------
  // Admin routes
  // ---------------------------------------------------------------------
  for (const r of [
    "/admin",
    "/admin/active",
    "/admin/queue",
    "/admin/deliverables",
    "/admin/risk-register",
    "/admin/audit",
    "/admin/management",
    "/admin/messages",
    "/admin/health",
  ]) {
    await warm(page, r, "admin");
  }

  for (const [kind, segment] of wanted) {
    const id = idFor[kind];
    if (!id) {
      timings.push({
        route: `/admin/services/[id]/${segment}`,
        group: "admin-service",
        cold: null,
        warm: null,
        note: `NOT WARMED — no service id for ${kind}`,
      });
      // eslint-disable-next-line no-console
      console.log(
        `warm: SKIPPED /admin/services/[id]/${segment} (no ${kind} id)`,
      );
      continue;
    }
    await warm(page, `/admin/services/${id}/${segment}`, "admin-service");
  }

  // ---------------------------------------------------------------------
  // Client-facing routes. Warmed while signed in as the consultant: the
  // POINT is compiling the route's code, and webpack does not care which
  // session requested it. What the page RENDERS under this session is not
  // what the demo shows, and this file asserts nothing about it.
  // ---------------------------------------------------------------------
  for (const r of [
    "/home",
    "/intake",
    "/assessments",
    "/results",
    "/documents",
    "/messages",
    "/account",
    "/dashboards/risk",
  ]) {
    await warm(page, r, "client");
  }

  for (const [kind, segment] of [
    ["TECH_DEBT", "tech-debt"],
    ["NIST_CSF", "csf"],
    ["ZERO_TRUST_CISA", "zt"],
    ["ATTACK_COVERAGE", "attack"],
  ] as Array<[string, string]>) {
    const id = idFor[kind];
    if (!id) {
      timings.push({
        route: `/dashboards/${segment}/[serviceId]`,
        group: "client-dashboard",
        cold: null,
        warm: null,
        note: `NOT WARMED — no service id for ${kind}`,
      });
      continue;
    }
    await warm(page, `/dashboards/${segment}/${id}`, "client-dashboard");
  }

  // ---------------------------------------------------------------------
  // Report
  // ---------------------------------------------------------------------
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const measured = timings.filter((t) => t.cold !== null && t.warm !== null);
  const unwarmed = timings.filter((t) => t.cold === null);
  const stillSlow = measured.filter((t) => (t.warm ?? 0) > 3000);
  const totalCold = measured.reduce((a, t) => a + (t.cold ?? 0), 0);
  const totalWarm = measured.reduce((a, t) => a + (t.warm ?? 0), 0);

  const lines: string[] = [
    `# Route warm-up — ${STAMP}`,
    ``,
    `Routes measured: ${measured.length}. Not warmed: ${unwarmed.length}.`,
    ``,
    `| route | group | cold (ms) | warm (ms) | saved (ms) | note |`,
    `| --- | --- | ---: | ---: | ---: | --- |`,
    ...timings.map((t) => {
      const saved =
        t.cold !== null && t.warm !== null ? String(t.cold - t.warm) : "—";
      return `| \`${t.route}\` | ${t.group} | ${t.cold ?? "—"} | ${t.warm ?? "—"} | ${saved} | ${t.note} |`;
    }),
    ``,
    `## Totals`,
    ``,
    `- Cold total: **${(totalCold / 1000).toFixed(1)}s**`,
    `- Warm total: **${(totalWarm / 1000).toFixed(1)}s**`,
    `- **Compile time removed from the take: ${((totalCold - totalWarm) / 1000).toFixed(1)}s**`,
    ``,
  ];

  if (stillSlow.length > 0) {
    lines.push(
      `## Slow on their ONE warm sample — CANDIDATES, not findings`,
      ``,
      `**Each figure below is a single draw, and a single timing is not a`,
      `property.** This spec visits routes back to back, so a route sampled`,
      `while a neighbour's compile is still finishing inherits that load —`,
      `a fact about WHEN it was measured, not about the route.`,
      ``,
      `Not hypothetical: the 2026-09-10T01:50 run flagged`,
      `\`zero-trust-cisa\` here at 8,233ms. Re-measured five times against two`,
      `control routes (\`engagement/zt-load-probe.spec.ts\`), its median was`,
      `**870ms**, against controls at 886ms and 876ms. The finding was an`,
      `artifact of this spec's own sampling, and it had already been written`,
      `into a demonstration plan before it was re-measured.`,
      ``,
      `**Re-measure with a distribution AND a control before acting on any row`,
      `below.** The control is what separates "this route is slow" from "the`,
      `machine was busy"; without one those are the same observation.`,
      ``,
      ...stillSlow.map(
        (t) => `- \`${t.route}\` — ${t.warm}ms on one sample. ${t.note}`,
      ),
      ``,
    );
  }

  if (unwarmed.length > 0) {
    lines.push(
      `## NOT WARMED — these will pay a cold compile on camera`,
      ``,
      ...unwarmed.map((t) => `- \`${t.route}\` — ${t.note}`),
      ``,
    );
  }

  fs.writeFileSync(
    path.join(OUT_DIR, "warm-routes.md"),
    lines.join("\n"),
    "utf8",
  );
  fs.writeFileSync(
    path.join(OUT_DIR, "warm-routes.json"),
    JSON.stringify({ stamp: STAMP, timings }, null, 2),
    "utf8",
  );

  // eslint-disable-next-line no-console
  console.log(`\nwarm-routes: report -> ${OUT_DIR}\n`);

  // The one thing worth failing on: a warm-up that warmed nothing has not done
  // its job, and reporting success would be the silent-success shape.
  expect(measured.length).toBeGreaterThan(0);
});
