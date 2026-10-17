import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { adminApiToken, API_BASE, atlasClientIdViaApi } from "../helpers/ids";
import { acknowledgeOfflineAi, waitForRun } from "../helpers/ai";
import { openSection } from "../helpers/sections";

/**
 * SMOKE_TEST.md section 5 (T6): the MITRE ATT&CK Coverage admin workspace.
 *
 * Admin opens the seeded Atlas ATT&CK service, runs the fixture-mode mitre_map
 * job (T6b), and works the matrix. We assert the spec's contract:
 *   1. The ATT&CK matrix + coverage-rollup heatmap render, Run AI reports
 *      "Mapping done for N tool(s) across M ATT&CK techniques and sub-techniques"
 *      (#1182; "tool" when N is 1), and a technique's side panel
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
    rationale: string | null;
    locked: boolean;
  }>;
}

/** Sign in, open the workspace, and layer a fresh draft assessment on top. */
async function openFreshDraft(
  page: Page,
  request: APIRequestContext,
): Promise<string> {
  // #1123 item 1: a plain create over released work is refused, and the
  // seeded Atlas ATT&CK service's only version is RELEASED. So this spec
  // mints a PRIVATE ATT&CK service under Atlas, as s11 does, and opens a
  // genuinely fresh draft on it (the changed>0 assertions need a clean grid).
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const svc = await (
    await request.post(`${API_BASE}/attack/services`, {
      headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId },
      data: { kind: "attack_coverage", title: "E2E ATT&CK Run AI" },
    })
  ).json();
  const attackServiceId = svc.id as string;
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${attackServiceId}/attack-coverage`);
  // The header only renders once EnsureActiveClient has set the active-client
  // cookie to Atlas, so the proxy POST below is correctly tenant-scoped.
  await expect(
    page.getByRole("heading", { level: 1, name: "Overview", exact: true }),
  ).toBeVisible({ timeout: 30000 });

  const created = await page.request.post(
    `/api/proxy/attack/services/${attackServiceId}/assessments`,
  );
  expect(created.ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
  // Let the (StrictMode-duplicated) initial loads finish so none of their
  // stale responses land mid-test and clobber fresher state.
  await page.waitForLoadState("networkidle").catch(() => undefined);
  return attackServiceId;
}

/**
 * Click Run AI, follow the run it starts to completion, and return what it
 * did with the assessment's coverage as it stands afterwards. #645: the POST
 * answers with a run id; the result is on the finished run, and the coverage
 * is re-read the way the workspace re-reads it.
 */
async function runAi(page: Page): Promise<RunAiBody> {
  const runStarted = page.waitForResponse(
    (r) =>
      r.url().includes("/attack/services/") &&
      r.url().includes("/run-ai") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "Run AI" }).click();
  // The offline guard intercepts the first click when no key is loaded.
  await acknowledgeOfflineAi(page);
  const started = (await (await runStarted).json()) as { run_id: string };
  const run = await waitForRun<Omit<RunAiBody, "coverage">>(
    page,
    started.run_id,
  );
  expect(run.status, `run ${run.id}: ${run.error_message}`).toBe("completed");
  // T6: the old workspace URL redirects into the client frame, which names
  // the service in `?service=`.
  const serviceId = new URL(page.url()).searchParams.get("service");
  expect(serviceId, "the workspace URL names the service").toBeTruthy();
  const latest = await page.request.get(
    `/api/proxy/attack/services/${serviceId}/assessments/latest`,
  );
  expect(latest.ok()).toBeTruthy();
  const { coverage } = (await latest.json()) as Pick<RunAiBody, "coverage">;
  return { ...(run.result as Omit<RunAiBody, "coverage">), coverage };
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
  request,
}) => {
  // Long flow (sign-in + create + run + reload) against a next-dev server that
  // is also serving the other smoke specs; triple the budget.
  test.slow();
  await openFreshDraft(page, request);

  // Matrix (Review) + coverage-rollup heatmap (Analysis) both render.
  await openSection(page, "Review");
  await expect(
    page.getByRole("heading", { name: "ATT&CK matrix" }),
  ).toBeVisible({ timeout: 30000 });
  await openSection(page, "Analysis");
  await expect(page.getByText("Coverage rollup")).toBeVisible();

  // Run AI is in AI draft (#1377).
  await openSection(page, "AI draft");
  const runBody = await runAi(page);
  expect(runBody.changed.length).toBeGreaterThan(0);
  expect(runBody.tools_available).toBeGreaterThan(0);

  // #1182: the workspace states what the run covered (Gene's line).
  const summary = page.getByTestId("attack-mapping-done");
  await expect(summary).toBeVisible({ timeout: 30000 });
  await expect(summary).toContainText(
    /Mapping done for \d+ tools? across \d+ ATT&CK techniques and sub-techniques\./,
  );

  // A STANDALONE technique (no sub-techniques, no parent) the fixture marked
  // covered with a cited tool. Not "T1001": since #554 (D-094) a parent with
  // sub-techniques is computed from them and the AI's suggestion for it is
  // refused whole, so it carries no fixture rationale. Derived from this run's
  // own rows, because batching decides which codes the fixture marks covered.
  const codes = runBody.coverage.map((c) => c.technique_code);
  const standalone = (code: string) =>
    !code.includes(".") && !codes.some((other) => other.startsWith(`${code}.`));
  const target = runBody.coverage.find(
    (c) =>
      standalone(c.technique_code) &&
      c.status === "covered" &&
      (c.detection_tools?.length ?? 0) > 0,
  );
  expect(target, "no standalone technique was marked covered").toBeTruthy();
  const targetCode = target?.technique_code as string;
  const expectedTool = target?.detection_tools?.[0];
  expect(expectedTool).toBeTruthy();

  // Assert the persisted result through a fresh load (race note above), then
  // open the technique panel and confirm D/P/R chips + rationale render. The
  // post-run reload re-renders the whole workspace, which can exceed 30s on a
  // loaded next-dev server.
  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 60000 });
  await openSection(page, "Review");
  await selectTechnique(page, targetCode);

  await expect(page.getByText("Detection", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.getByText("Prevention", { exact: true })).toBeVisible();
  await expect(page.getByText("Response", { exact: true })).toBeVisible();
  await expect(page.getByText(expectedTool as string).first()).toBeVisible();
  await expect(
    page.getByText(`Fixture-mode draft coverage assessment for ${targetCode}.`),
  ).toBeVisible();
});

test("a locked technique is untouched by Run AI and absent from the what-changed diff (C2)", async ({
  page,
  request,
}) => {
  // Long flow with two auto-save PATCHes; next-dev queues requests for tens of
  // seconds when the other smoke specs share the server, so triple the budget.
  test.slow();
  await openFreshDraft(page, request);

  // A STANDALONE technique: T1003 has sub-techniques, so since #554 (D-094)
  // its status is computed and the status radios are disabled.
  const LOCK_CODE = "T1190";

  // Select the technique, set a known status (Gap), and lock it BEFORE Run AI.
  // The matrix and the technique panel are in Review (#1377).
  await openSection(page, "Review");
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

  // Run AI: unlocked rows change; the locked row must be skipped. It is in
  // AI draft (#1377).
  await openSection(page, "AI draft");
  const runBody = await runAi(page);

  // Other (unlocked) techniques were updated...
  expect(runBody.changed.length).toBeGreaterThan(0);
  // ...but the locked technique is absent from the what-changed diff...
  expect(
    runBody.changed.filter((c) => c.technique_code === LOCK_CODE),
  ).toHaveLength(0);
  // ...and its row kept the manual "gap" status. The status alone cannot
  // prove the AI was held off -- the fixture's cycle might map this code to
  // "gap" too -- but the fixture writes its rationale on EVERY row it touches,
  // so the absence of that rationale is the proof.
  const lockedRow = runBody.coverage.find(
    (c) => c.technique_code === LOCK_CODE,
  );
  expect(lockedRow?.locked).toBe(true);
  expect(lockedRow?.status).toBe("gap");
  expect(lockedRow?.rationale ?? "").not.toContain("Fixture-mode draft");
});
