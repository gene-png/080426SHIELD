import { expect, test } from "@playwright/test";

import { signIn } from "../helpers/auth";

/**
 * How does `/admin/management` scale with tenant count?
 *
 * ## Why this exists
 *
 * #111 has carried `1 + 2N` since 2026-08-21 with exactly TWO measured points
 * — 5.4s at 3 clients and 95.6s at 88. Two points cannot establish a curve, and
 * they do not obviously agree: 29x the clients for 18x the time is SUBLINEAR,
 * while a trace of one real load shows mean 2739ms against median 1695ms, which
 * is contention and argues the other way. Nothing between 3 and 88 has ever been
 * measured.
 *
 * The decision waiting on this has been open in `context/gene.md` for nineteen
 * days as "whether #111 gets pulled ahead". It has been framed as a forecast —
 * what tenant count is realistic — which is a question nobody can answer from
 * here. The answerable version is: **at what N does this page stop being
 * usable?** Then the business question collapses to "will you have more than N
 * clients", which is a yes or no.
 *
 * ## What it measures, and what it does NOT
 *
 * Three numbers per run: time to the `h1`, time to `networkidle`, and the
 * request count. N is whatever the database holds — this spec does not seed. Set
 * N externally between runs and collect the rows.
 *
 * **These are DEV-MODE numbers and they are an upper bound, not the product's.**
 * Next dev latency was measured the same day at ~500ms per proxied call against
 * 5-19ms direct, and React StrictMode double-invokes effects in development, so
 * the observed request count is `1 + 4N` where production is `1 + 2N`. Both
 * inflations are recorded rather than corrected for, because a correction factor
 * would be a guess. What survives the environment is the SHAPE of the curve, and
 * #111's existing points appear to come from the same dev harness, so the rows
 * are comparable to those.
 *
 * A production threshold needs a built app. This does not provide one and does
 * not claim to.
 *
 * ## Asserts almost nothing, on purpose
 *
 * The only assertion is that the page rendered at all. A threshold assertion
 * here would encode today's hardware into a gate, and the question is what the
 * number IS, not whether it is under a line somebody guessed.
 */

const ADMIN = "admin@kentro.example";
const PASSWORD = "DemoPass!2026";
const IDLE_CAP_MS = 180_000;

test.skip(
  process.env.SHIELD_MGMT_SCALING !== "1",
  "Opt-in scaling measurement for #111; set SHIELD_MGMT_SCALING=1.",
);

test("how long does /admin/management take at the current tenant count", async ({
  page,
}) => {
  test.setTimeout(IDLE_CAP_MS + 120_000);

  await signIn(page, ADMIN, PASSWORD);

  let requests = 0;
  const perClient = new Set<string>();
  page.on("request", (r) => {
    const u = r.url();
    if (!u.includes("/api/proxy/admin/clients/")) return;
    requests += 1;
    const m = /\/clients\/([0-9a-f-]+)\//.exec(u);
    if (m) perClient.add(m[1]);
  });

  const t0 = Date.now();
  await page.goto("/admin/management");
  await expect(
    page.getByRole("heading", { name: "Management", level: 1 }),
  ).toBeVisible();
  const heading = Date.now() - t0;

  let idle: number | null = null;
  try {
    await page.waitForLoadState("networkidle", { timeout: IDLE_CAP_MS });
    idle = Date.now() - t0;
  } catch {
    idle = null; // never settled inside the cap; report that, do not guess
  }

  // The row. Deliberately one line so a set of runs greps into a table.
  console.log(
    `MGMT-SCALING clients=${perClient.size} requests=${requests} ` +
      `heading_ms=${heading} idle_ms=${idle ?? "NEVER"} cap_ms=${IDLE_CAP_MS}`,
  );
});
