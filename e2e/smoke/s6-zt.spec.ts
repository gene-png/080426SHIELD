import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { atlasServiceId } from "../helpers/ids";

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
async function openFreshDraft(page: Page): Promise<void> {
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  // Seeded Atlas Defense "Zero Trust (DoD ZTRA)" service (scripts/seed_demo.py).
  const ztDodServiceId = await atlasServiceId(page, "zero_trust_dod");
  await page.goto(`/admin/services/${ztDodServiceId}/zero-trust-dod`);
  await expect(
    page.getByRole("heading", {
      name: "Zero Trust Assessment — DoD Reference Architecture",
    }),
  ).toBeVisible({ timeout: 30000 });

  // Close any open draft first, then mint. SPRINT_3 T1 added a draft-exists
  // guard: POST now REUSES an open draft instead of minting a new version, so a
  // plain POST would hand back a previous run's already-AI-drafted draft and
  // Run AI would diff to zero changes (the changed>0 assertion below needs a
  // clean grid). Approving moves any open DRAFT out of DRAFT (ignored when
  // nothing is open), so the following POST cuts a genuinely fresh v+1.
  const prior = await page.request.get(
    `/api/proxy/zt/services/${ztDodServiceId}/assessments/latest`,
  );
  if (prior.ok()) {
    const p = (await prior.json()) as { id: string; status: string };
    if (p.status === "draft") {
      await page.request.post(`/api/proxy/zt/assessments/${p.id}/approve`);
    }
  }
  const created = await page.request.post(
    `/api/proxy/zt/services/${ztDodServiceId}/assessments`,
  );
  expect(created.ok()).toBeTruthy();

  await page.reload();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
  // Let the (StrictMode-duplicated) initial loads finish so none of their
  // stale responses land mid-test and clobber fresher state.
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

test("DoD questionnaire renders by pillar and current/target stages are settable", async ({
  page,
}) => {
  // Long flow (sign-in + create + reload + two auto-save PATCHes) against a
  // next-dev server that is also serving the other smoke specs; a queued PATCH
  // can take tens of seconds under load, so triple the budget.
  test.slow();
  await openFreshDraft(page);

  // The questionnaire renders, grouped into pillar tabs.
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
}) => {
  // Long flow (sign-in + create + reload + Run AI, all against a next-dev server
  // that cold-compiles routes and queues requests under whole-suite load); the
  // sibling test above uses the same budget, so triple the default timeout.
  test.slow();
  await openFreshDraft(page);

  // Run the fixture AI and capture the what-changed payload.
  const runDone = page.waitForResponse(
    (r) =>
      r.url().includes("/zt/services/") &&
      r.url().includes("/run-ai") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "Run AI" }).click();
  const runBody = (await (await runDone).json()) as {
    changed: Array<{
      capability_code: string;
      field: string;
      new: number | null;
    }>;
  };

  // Suggestions were applied...
  expect(runBody.changed.length).toBeGreaterThan(0);
  // ...and every drafted stage (current or target) respects the DoD <= 3 clamp.
  const stageValues = runBody.changed
    .map((c) => c.new)
    .filter((v): v is number => typeof v === "number");
  expect(stageValues.length).toBeGreaterThan(0);
  for (const v of stageValues) {
    expect(v).toBeLessThanOrEqual(3);
  }

  // The workspace echoes the "Updated N fields across M capabilities" summary.
  const summary = page
    .locator("p", { hasText: "Updated" })
    .filter({ hasText: "capabilit" });
  await expect(summary).toBeVisible({ timeout: 30000 });

  // Remediation gaps surface and the 12-month roadmap sequences them by month.
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
