import { test, expect } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";

/**
 * Re-measure the two slow Zero Trust admin routes, with a distribution and a
 * control.
 *
 * ## Why this exists
 *
 * `warm-routes.spec.ts` reported `/admin/services/[id]/zero-trust-cisa` at
 * 8,233ms WARM against 7,212ms cold — slower on its second visit than its
 * first — and `zero-trust-dod` at 5,476ms warm, while every other route in the
 * run landed under 2.3s warm and most under 1s.
 *
 * That is a striking result and it rests on **exactly one warm measurement per
 * route**. A single timing is not a property; it is one draw. Before any of it
 * is written into a demonstration plan — or filed as a product finding — it
 * gets a distribution.
 *
 * ## The control is the point
 *
 * `attack-coverage` is measured in the same loop, on the same session, against
 * the same seeded client. It came back at 915ms warm in the same run. If the
 * ZT routes are genuinely slow, the control stays fast and the gap is real. If
 * the whole box is loaded and everything is slow, the control says so and the
 * ZT numbers mean nothing in particular.
 *
 * Without it, a slow run of the machine and a slow route are the same
 * observation.
 */

test.skip(
  process.env.SHIELD_ZT_PROBE !== "1",
  "Targeted ZT load measurement; set SHIELD_ZT_PROBE=1.",
);

test.use({ viewport: { width: 1920, height: 1080 } });

const PASSES = 5;

interface Sample {
  label: string;
  ms: number[];
}

function summarise(s: Sample): string {
  const sorted = [...s.ms].sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const median = sorted[Math.floor(sorted.length / 2)];
  const mean = Math.round(s.ms.reduce((a, b) => a + b, 0) / s.ms.length);
  return `${s.label.padEnd(20)} n=${s.ms.length} min=${min} median=${median} mean=${mean} max=${max}  observed=[${s.ms.join(", ")}]`;
}

test("ZT admin workspace load — distribution against a control", async ({
  page,
}) => {
  test.setTimeout(15 * 60_000);

  const ids = process.env.SHIELD_WARM_SERVICE_IDS ?? "";
  const idFor: Record<string, string> = {};
  for (const pair of ids.split(",")) {
    const [k, v] = pair.split("=");
    if (k && v) idFor[k.trim()] = v.trim();
  }

  const targets: Array<[string, string]> = [
    ["zt-cisa", `/admin/services/${idFor.ZERO_TRUST_CISA}/zero-trust-cisa`],
    ["zt-dod", `/admin/services/${idFor.ZERO_TRUST_DOD}/zero-trust-dod`],
    // The control.
    [
      "attack (control)",
      `/admin/services/${idFor.ATTACK_COVERAGE}/attack-coverage`,
    ],
    ["tech-debt (control)", `/admin/services/${idFor.TECH_DEBT}/tech-debt`],
  ];

  expect(
    Object.keys(idFor).length,
    "SHIELD_WARM_SERVICE_IDS must be set — measuring undefined routes would produce a confident number about a 404",
  ).toBeGreaterThan(0);

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  // Warm all of them once first, so no sample carries a compile.
  for (const [, url] of targets) {
    await page.goto(url, { timeout: 120_000, waitUntil: "domcontentloaded" });
  }

  const samples: Sample[] = targets.map(([label]) => ({ label, ms: [] }));

  // INTERLEAVED, not grouped. Measuring all five ZT passes and then all five
  // control passes would confound the route with whatever else the machine was
  // doing during each block — the two variables would move together and could
  // not be separated afterwards.
  for (let pass = 0; pass < PASSES; pass++) {
    for (let i = 0; i < targets.length; i++) {
      const [, url] = targets[i];
      const t0 = Date.now();
      await page.goto(url, { timeout: 120_000, waitUntil: "domcontentloaded" });
      samples[i].ms.push(Date.now() - t0);
    }
  }

  // eslint-disable-next-line no-console
  console.log("\n=== ZT load probe ===");
  for (const s of samples) {
    // eslint-disable-next-line no-console
    console.log(summarise(s));
  }
  // eslint-disable-next-line no-console
  console.log("");

  expect(samples.every((s) => s.ms.length === PASSES)).toBe(true);
});
