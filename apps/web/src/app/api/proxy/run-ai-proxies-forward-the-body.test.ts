import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every Run-AI proxy forwards the request body (#645, #504).
 *
 * The body carries `serves`, the AI status the consultant acknowledged, and
 * the api refuses a Run-AI without it. Three of these proxies were written as
 * `proxyJson(url, { method: "POST" })`, which drops the body: every Run-AI
 * through them would be refused with `serves_required`, and no unit test could
 * see it, because the workspaces' tests mock the client above the proxy.
 *
 * Derived from the directory, so a fifth Run-AI proxy is covered the day it is
 * added: any route under `api/proxy` whose path ends in `run-ai` or in the Tech
 * Debt `capability-lists/extract`.
 */
const PROXY_ROOT = join(process.cwd(), "src/app/api/proxy");

function routeFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...routeFiles(p));
    else if (entry === "route.ts") out.push(p);
  }
  return out;
}

const RUN_AI_ROUTE =
  /[\\/](run-ai|capability-lists[\\/]extract)[\\/]route\.ts$/;

describe("Run-AI proxies forward the body (#645)", () => {
  const runAiRoutes = routeFiles(PROXY_ROOT).filter((p) =>
    RUN_AI_ROUTE.test(p),
  );

  it("finds the Run-AI proxies at all", () => {
    // ATT&CK, CSF and ZT run-ai, and the Tech Debt extraction. A filter that
    // matches nothing would pass the test below vacuously.
    expect(runAiRoutes.length).toBeGreaterThanOrEqual(4);
  });

  it("forwards the request body in every one of them", () => {
    const dropping = runAiRoutes
      .filter((p) => !readFileSync(p, "utf8").includes("proxyJsonFromRequest("))
      .map((p) => relative(PROXY_ROOT, p));
    expect(
      dropping,
      "these Run-AI proxies do not forward the body, so `serves` never reaches the api",
    ).toEqual([]);
  });
});
