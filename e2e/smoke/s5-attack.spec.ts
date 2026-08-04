import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { atlasServiceId } from "../helpers/ids";

/**
 * SMOKE_TEST.md section 5 (T6): the MITRE ATT&CK Coverage admin workspace.
 *
 * Admin opens the seeded Atlas ATT&CK service, runs the fixture-mode mitre_map
 * job (T6b), and works the matrix. We assert the spec's contract:
 *   1. The ATT&CK matrix + coverage-rollup heatmap render, Run AI reports
 *      "Updated N fields across M techniques", and a technique's side panel
 *      shows its Detection/Prevention/Response tool chips + rationale.
 *   2. C2 lock semantics: a locked technique is left untouched by a Run AI and
 *      is absent from the "what changed" diff, while unlocked rows still change.
 *
 * The seeded assessment is RELEASED (read-only: Run AI + locking disabled), so
 * each test first mints a fresh DRAFT via the proxy — the active-client cookie
 * is already aligned to Atlas by EnsureActiveClient once the workspace header
 * renders — then reloads so the workspace picks the draft up.
 *
 * Race note: next-dev + React StrictMode double-runs the workspace's initial
 * load; a slow duplicate "latest assessment" response can land AFTER Run AI's
 * refetch and clobber the fresh rows (heatmap state lives separately, so it
 * keeps the new numbers). The spec therefore (a) settles the network before
 * interacting and (b) asserts post-run UI state after a reload, where a fresh
 * initial load renders straight from the committed DB state.
 */

interface RunAiBody {
  tools_available: number;
  changed: Array<{ technique_code: string; field: string }>;
  coverage: Array<{
    technique_code: string;
    status: string | null;
    detection_tools: string[] | null;
    locked: boolean;
  }>;
}

/** Sign in, open the workspace, and layer a fresh draft assessment on top. */
async function openFreshDraft(page: Page): Promise<void> {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  // Seeded Atlas Defense "MITRE ATT&CK Coverage" service (scripts/seed_demo.py).
  const attackServiceId = await atlasServiceId(page, "attack_coverage");
  await page.goto(`/admin/services/${attackServiceId}/attack-coverage`);
  // The header only renders once EnsureActiveClient has set the active-client
  // cookie to Atlas, so the proxy POST below is correctly tenant-scoped.
  await expect(
    page.getByRole("heading", { name: "MITRE ATT&CK Coverage" }),
  ).toBeVisible({ timeout: 30000 });

  // Discard any open draft first, then mint. SPRINT_3 T1 added a draft-exists
  // guard: POST now REUSES an open draft instead of minting a new version, so a
  // plain POST would hand back a previous run's already-AI-drafted draft and
  // Run AI would diff to zero changes (the changed>0 assertions below need a
  // clean grid). Discarding throws any open DRAFT away (Sprint 9 T0 / D-031;
  // ignored when nothing is open), so the following POST cuts a genuinely fresh
  // draft — this retires the old approve-first dance.
  const prior = await page.request.get(
    `/api/proxy/attack/services/${attackServiceId}/assessments/latest`,
  );
  if (prior.ok()) {
    const p = (await prior.json()) as { id: string; status: string };
    if (p.status === "draft") {
      await page.request.post(`/api/proxy/attack/assessments/${p.id}/discard`);
    }
  }
  const created = await page.request.post(
    `/api/proxy/attack/services/${attackServiceId}/assessments`,
  );
  expect(created.ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
  // Let the (StrictMode-duplicated) initial loads finish so none of their
  // stale responses land mid-test and clobber fresher state.
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

/** Click Run AI and return the parsed run-ai response body. */
async function runAi(page: Page): Promise<RunAiBody> {
  const runDone = page.waitForResponse(
    (r) =>
      r.url().includes("/attack/services/") &&
      r.url().includes("/run-ai") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "Run AI" }).click();
  return (await (await runDone).json()) as RunAiBody;
}

/** Select a technique cell in the matrix by its exact code. */
async function selectTechnique(page: Page, code: string): Promise<void> {
  await page
    .getByRole("button")
    .filter({ has: page.getByText(code, { exact: true }) })
    .first()
    .click();
}

test("matrix + heatmap render, Run AI reports updated fields, and the panel shows D/P/R + rationale", async ({
  page,
}) => {
  // Long flow (sign-in + create + run + reload) against a next-dev server that
  // is also serving the other smoke specs; triple the budget.
  test.slow();
  await openFreshDraft(page);

  // Matrix + coverage-rollup heatmap both render.
  await expect(
    page.getByRole("heading", { name: "ATT&CK matrix" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Coverage rollup")).toBeVisible();

  const runBody = await runAi(page);
  expect(runBody.changed.length).toBeGreaterThan(0);
  expect(runBody.tools_available).toBeGreaterThan(0);

  // The workspace echoes the "Updated N fields across M techniques" summary.
  const summary = page
    .locator("p", { hasText: "Updated" })
    .filter({ hasText: "technique" });
  await expect(summary).toBeVisible({ timeout: 30000 });
  await expect(summary).toContainText(/Updated\s+\d+\s+field/);

  // T1001 sorts first, so the fixture deterministically marks it covered and
  // cites a detection tool validated against the client's Tech Debt list.
  const t1001 = runBody.coverage.find((c) => c.technique_code === "T1001");
  expect(t1001?.status).toBe("covered");
  const expectedTool = t1001?.detection_tools?.[0];
  expect(expectedTool).toBeTruthy();

  // Assert the persisted result through a fresh load (race note above), then
  // open the technique panel and confirm D/P/R chips + rationale render. The
  // post-run reload re-renders the whole workspace, which can exceed 30s on a
  // loaded next-dev server.
  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 60000 });
  await selectTechnique(page, "T1001");

  await expect(page.getByText("Detection", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText("Prevention", { exact: true })).toBeVisible();
  await expect(page.getByText("Response", { exact: true })).toBeVisible();
  await expect(page.getByText(expectedTool as string).first()).toBeVisible();
  await expect(
    page.getByText(/Fixture-mode draft coverage assessment for T1001/),
  ).toBeVisible();
});

test("a locked technique is untouched by Run AI and absent from the what-changed diff (C2)", async ({
  page,
}) => {
  // Long flow with two auto-save PATCHes; next-dev queues requests for tens of
  // seconds when the other smoke specs share the server, so triple the budget.
  test.slow();
  await openFreshDraft(page);

  const LOCK_CODE = "T1003";

  // Select the technique, set a known status (Gap), and lock it BEFORE Run AI.
  await selectTechnique(page, LOCK_CODE);

  const statusGroup = page.getByRole("radiogroup", { name: "Coverage status" });
  await expect(statusGroup).toBeVisible({ timeout: 15000 });
  const statusPatched = page.waitForResponse(
    (r) =>
      r.url().includes("/attack/coverage/") &&
      r.request().method() === "PATCH" &&
      r.ok(),
    { timeout: 90000 },
  );
  await statusGroup.getByRole("radio", { name: "Gap" }).click();
  await statusPatched;

  const lockPatched = page.waitForResponse(
    (r) =>
      r.url().includes("/attack/coverage/") &&
      r.request().method() === "PATCH" &&
      r.ok(),
    { timeout: 90000 },
  );
  await page.getByRole("checkbox", { name: /Lock this technique/ }).check();
  await lockPatched;

  // Run AI: unlocked rows change; the locked row must be skipped.
  const runBody = await runAi(page);

  // Other (unlocked) techniques were updated...
  expect(runBody.changed.length).toBeGreaterThan(0);
  // ...but the locked technique is absent from the what-changed diff...
  expect(
    runBody.changed.filter((c) => c.technique_code === LOCK_CODE),
  ).toHaveLength(0);
  // ...and its row kept the manual "gap" status the AI would otherwise
  // overwrite (the fixture's status cycle maps an unlocked T1003 to a
  // different status, so this would provably have changed).
  const lockedRow = runBody.coverage.find(
    (c) => c.technique_code === LOCK_CODE,
  );
  expect(lockedRow?.locked).toBe(true);
  expect(lockedRow?.status).toBe("gap");
});
