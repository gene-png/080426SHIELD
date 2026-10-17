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
 * SMOKE_TEST.md section 6 (T6): the Zero Trust (DoD ZTRA) admin workspace.
 *
 * Admin opens the seeded Atlas DoD Zero Trust service and runs the fixture-mode
 * zt_score job (T6b). We assert the spec's contract:
 *   1. The questionnaire renders by pillar (a tablist), and current/target
 *      stages are settable per capability.
 *   2. Run AI applies suggestions with the DoD ladder clamped to <= 3 (the DoD
 *      ZTRA scale is 3 stages; code drops anything the AI drafts above it).
 *   3. Remediation gaps surface and the 12-month roadmap groups them by month.
 *
 * The seeded assessment is RELEASED (read-only: Run AI disabled), so the test
 * mints a fresh DRAFT via the proxy — the active-client cookie is aligned to
 * Atlas by EnsureActiveClient once the header renders — then reloads.
 */

/** Sign in, open the DoD workspace, and layer a fresh draft assessment on top. */
async function openFreshDraft(
  page: Page,
  request: APIRequestContext,
): Promise<string> {
  // #1123 item 1: a plain create over released work is refused, and the
  // seeded Atlas DoD service's only version is RELEASED. So this spec mints a
  // PRIVATE DoD service under Atlas, as s11 does for ATT&CK, and opens a
  // genuinely fresh draft on it (the changed>0 assertion needs a clean grid).
  const token = await adminApiToken(request);
  const clientId = await atlasClientIdViaApi(request, token);
  const svc = await (
    await request.post(`${API_BASE}/zt/services`, {
      headers: { Authorization: `Bearer ${token}`, "X-Client-Id": clientId },
      data: { kind: "zero_trust_dod", title: "E2E Zero Trust DoD" },
    })
  ).json();
  const ztDodServiceId = svc.id as string;
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/admin/services/${ztDodServiceId}/zero-trust-dod`);
  // #1379: the old URL lands on Overview, whose section header is the page's
  // h1; each block is in its own section, opened through the section bar.
  await expect(
    page.getByRole("heading", { level: 1, name: "Overview", exact: true }),
  ).toBeVisible({ timeout: 30000 });

  const created = await page.request.post(
    `/api/proxy/zt/services/${ztDodServiceId}/assessments`,
  );
  expect(created.ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
  // Let the (StrictMode-duplicated) initial loads finish so none of their
  // stale responses land mid-test and clobber fresher state.
  await page.waitForLoadState("networkidle").catch(() => undefined);
  return ztDodServiceId;
}

test("DoD questionnaire renders by pillar and current/target stages are settable", async ({
  page,
  request,
}) => {
  // Long flow (sign-in + create + reload + two auto-save PATCHes) against a
  // next-dev server that is also serving the other smoke specs; a queued PATCH
  // can take tens of seconds under load, so triple the budget.
  test.slow();
  await openFreshDraft(page, request);

  // The questionnaire (in Review) renders, grouped into pillar tabs.
  await openSection(page, "Review");
  await expect(
    page.getByRole("heading", { name: "Zero Trust questionnaire" }),
  ).toBeVisible({ timeout: 30000 });
  const pillarTabs = page
    .getByRole("tablist", { name: "Zero Trust pillars" })
    .getByRole("tab");
  expect(await pillarTabs.count()).toBeGreaterThanOrEqual(2);

  // The DoD ladder is exactly 3 stages, so each maturity picker offers 3 radios.
  const maturity = page
    .getByRole("radiogroup", { name: /Maturity stage for/i })
    .first();
  await expect(maturity.getByRole("radio")).toHaveCount(3);

  // Set a current maturity stage (S2) — it persists via an auto-save PATCH.
  const currentSaved = page.waitForResponse(
    (r) =>
      r.url().includes("/zt/answers/") &&
      r.request().method() === "PATCH" &&
      r.ok(),
    { timeout: 60000 },
  );
  await maturity.getByRole("radio").nth(1).click();
  await currentSaved;
  await expect(maturity.getByRole("radio").nth(1)).toHaveAttribute(
    "aria-checked",
    "true",
  );

  // Set a target stage (L3) on the same capability. The UI updates
  // optimistically before the PATCH resolves, so wait on the network response
  // (generously — next-dev queues requests under load) before asserting.
  const targetSaved = page.waitForResponse(
    (r) =>
      r.url().includes("/zt/answers/") &&
      r.request().method() === "PATCH" &&
      r.ok(),
    { timeout: 90000 },
  );
  const targetSelect = page
    .getByRole("combobox", { name: /Target stage for/i })
    .first();
  await targetSelect.selectOption("3");
  await targetSaved;
  await expect(targetSelect).toHaveValue("3");

  // Arrow-key roving tabindex on the ZtStagePicker radiogroup (WAI-ARIA pattern,
  // T6 — identical semantics to the CSF TierPicker asserted in s12, backfilled
  // here so the DoD stage picker has its own regression net). Arrows move focus
  // and the roving Tab stop (tabindex=0) only; selection stays on Space/Enter so
  // auto-save PATCHes aren't flooded, so aria-checked must NOT change on arrow.
  const stageRadios = maturity.getByRole("radio");
  const stageCount = await stageRadios.count();
  expect(stageCount, "ZtStagePicker exposes multiple radios").toBeGreaterThan(
    1,
  );

  // ArrowRight: focus + roving stop move from the first radio to the second.
  await stageRadios.nth(0).focus();
  const stageCheckedBefore = await stageRadios
    .nth(1)
    .getAttribute("aria-checked");
  await page.keyboard.press("ArrowRight");
  await expect(stageRadios.nth(1)).toBeFocused();
  await expect(stageRadios.nth(1)).toHaveAttribute("tabindex", "0");
  await expect(stageRadios.nth(0)).toHaveAttribute("tabindex", "-1");
  // The arrow did not toggle selection on the newly focused radio.
  await expect(stageRadios.nth(1)).toHaveAttribute(
    "aria-checked",
    stageCheckedBefore ?? "false",
  );

  // ArrowLeft: move back to the first radio; the roving stop follows.
  await page.keyboard.press("ArrowLeft");
  await expect(stageRadios.nth(0)).toBeFocused();
  await expect(stageRadios.nth(0)).toHaveAttribute("tabindex", "0");
  await expect(stageRadios.nth(1)).toHaveAttribute("tabindex", "-1");

  // Wrap-around: ArrowLeft from the first radio lands on the last.
  await page.keyboard.press("ArrowLeft");
  await expect(stageRadios.nth(stageCount - 1)).toBeFocused();
  await expect(stageRadios.nth(stageCount - 1)).toHaveAttribute(
    "tabindex",
    "0",
  );
});

test("Run AI clamps DoD suggestions to <= 3 and the roadmap groups gaps by month", async ({
  page,
  request,
}) => {
  // Long flow (sign-in + create + reload + Run AI, all against a next-dev server
  // that cold-compiles routes and queues requests under whole-suite load); the
  // sibling test above uses the same budget, so triple the default timeout.
  test.slow();
  const ztDodServiceId = await openFreshDraft(page, request);

  // #806: the approved prompt gives no result for a capability with blank
  // notes (A5), and the fixture follows it, so a BLANK draft would change
  // nothing. Record notes on three capabilities first, through the same API
  // the questionnaire's notes field saves to; the run under test is the AI's.
  // Three capabilities of the FIRST pillar, which is the tab the questionnaire
  // opens on, so the notes can be checked on screen below.
  const catalogRes = await page.request.get(
    "/api/proxy/zt/catalog?framework=dod_ztra",
  );
  expect(catalogRes.ok()).toBeTruthy();
  const catalog = (await catalogRes.json()) as {
    pillars: Array<{ capabilities: Array<{ code: string }> }>;
  };
  const noted = catalog.pillars[0].capabilities.slice(0, 3).map((c) => c.code);
  expect(noted).toHaveLength(3);
  const latest = await page.request.get(
    `/api/proxy/zt/services/${ztDodServiceId}/assessments/latest`,
  );
  expect(latest.ok()).toBeTruthy();
  const draft = (await latest.json()) as {
    answers: Array<{ id: string; capability_code: string }>;
  };
  const NOTE = "MFA is enforced for every workforce account.";
  for (const code of noted) {
    const answer = draft.answers.find((a) => a.capability_code === code);
    expect(answer, `no answer row for ${code}`).toBeTruthy();
    const saved = await page.request.patch(
      `/api/proxy/zt/answers/${answer!.id}`,
      { data: { notes: NOTE } },
    );
    expect(saved.ok()).toBeTruthy();
  }
  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
  // The setup reached the screen the run reads from (#736 comment
  // 6073312727): each note is visible in its capability's notes field, opened
  // from its collapsed summary. The questionnaire is in Review.
  await openSection(page, "Review");
  for (const code of noted) {
    const field = page.getByLabel(`Notes for ${code}`, { exact: true });
    await page.locator("details", { has: field }).locator("summary").click();
    await expect(field).toBeVisible({ timeout: 30000 });
    await expect(field).toHaveValue(NOTE);
  }

  // Run the fixture AI and capture the what-changed payload (AI draft).
  await openSection(page, "AI draft");
  const runDone = page.waitForResponse(
    (r) =>
      r.url().includes("/zt/services/") &&
      r.url().includes("/run-ai") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "Run AI" }).click();
  await acknowledgeOfflineAi(page);
  // #645: the POST starts a run; what it changed is on the completed run.
  const started = (await (await runDone).json()) as { run_id: string };
  const run = await waitForRun<{
    changed: Array<{
      capability_code: string;
      field: string;
      new: number | null;
    }>;
  }>(page, started.run_id);
  expect(run.status, `run ${run.id}: ${run.error_message}`).toBe("completed");
  const runBody = run.result as NonNullable<typeof run.result>;

  // Suggestions were applied...
  expect(runBody.changed.length).toBeGreaterThan(0);
  // ...and every drafted stage respects the DoD <= 3 clamp. Since #806 the AI
  // drafts a current stage only, never a target.
  const stageValues = runBody.changed
    .map((c) => c.new)
    .filter((v): v is number => typeof v === "number");
  expect(stageValues.length).toBeGreaterThan(0);
  for (const v of stageValues) {
    expect(v).toBeLessThanOrEqual(3);
  }

  // The panel accounts for every suggestion the run received (W1, issue #44),
  // not just the ones that landed — this replaced the old "Updated N fields
  // across M capabilities" line.
  //
  // NOTE: this spec mints a BLANK draft and records notes only, so every row is
  // unanswered and nothing is protected; the fixture then answers the noted
  // rows with in-range values, so this run has zero drops and can only prove
  // the accounting line renders. The VALIDATION drop branches are covered in
  // ZtRunAiAccounting.test.tsx and the API unit tests.
  //
  // Round 2 correction: "fixture mode cannot produce a drop" is false for ZT.
  // `protected` is fixture-ONLY (`protected_keys` returns an empty set
  // off-fixture), so a run over a client-submitted assessment WOULD surface a
  // drop here end to end. This spec deliberately avoids that state, so the one
  // reason it could prove, it does not. Worth a spec of its own.
  //
  // The wording is "suggested values", NOT CSF's "suggested score values": ZT's
  // narrative fields were removed rather than counted (#64), so there is no
  // non-score category here to distinguish against.
  const summary = page
    .locator("p", { hasText: /AI applied \d+ of \d+ suggested value/ })
    .filter({ hasText: "capabilit" });
  await expect(summary.first()).toBeVisible({ timeout: 30000 });

  // The AI-provenance notice stands beside the accounting on every run (#68).
  // This is the ZT wiring proof — there is no ZtWorkspace vitest harness, so
  // the component's own tests cannot show it is actually rendered here.
  //
  // Unlike the drop branches, fixture mode CAN prove this one end to end: the
  // notice is unconditional, so it does not depend on a rejected suggestion.
  await expect(
    page.getByText(/informed by client-submitted input/).first(),
  ).toBeVisible({ timeout: 30000 });

  // Remediation gaps surface and the 12-month roadmap sequences them by month
  // (Analysis).
  await openSection(page, "Analysis");
  await expect(
    page.getByRole("heading", { name: "Remediation gaps" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    page.getByRole("heading", { name: "12-month roadmap" }),
  ).toBeVisible();
  await expect(page.getByText(/^Month \d+$/).first()).toBeVisible({
    timeout: 30000,
  });
});
