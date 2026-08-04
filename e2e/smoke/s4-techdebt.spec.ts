import { expect, test } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { atlasServiceId } from "../helpers/ids";

/**
 * SMOKE_TEST.md section 4 (T6): the Tech Debt admin workspace.
 *
 * Admin opens the seeded Atlas Tech Debt service, uploads an inventory CSV, and
 * the fixture-mode AI (T6b) extracts a fresh DRAFT capability list — one row per
 * CSV line, each stamped with an AI confidence percentage. We assert the spec's
 * two contract points:
 *   1. The dashboard summarizes the extracted list (capability count, annual
 *      cost, categories, to-consolidate/cut, low-confidence counts).
 *   2. Editing any cell clears that row's AI-confidence badge and re-labels it
 *      "Human-curated" (the API sets confidence_pct = NULL on a human edit).
 *
 * Draft-exists contract (Sprint 8 T1, commit 4396f60): a POST to /extract while a
 * DRAFT capability list is already open now REUSES that draft (idempotent 200)
 * instead of minting a fresh version — matching CSF / ATT&CK / Zero Trust. This
 * spec edits a row on the draft it extracts, so on the shared seeded DB a plain
 * re-run would hand back that already-curated draft and the "AI 60%" row would be
 * gone. The spec therefore DISCARDS any open draft first (Sprint 9 T0 / D-031 —
 * the discard affordance retires the old approve-first dance), so the upload's
 * extraction cuts a genuinely fresh four-row draft and the "AI 60%" row stays
 * deterministic across re-runs — the s5-attack.spec.ts openFreshDraft pattern
 * applied to tech-debt.
 */

// A tiny inventory. The fixture extractor reads the redacted rows and stamps a
// deterministic confidence per row (60, 70, 80, 90) — so exactly one row is
// "AI 60%", which we edit to prove the badge clears.
const INVENTORY_CSV =
  "name,vendor,category,annual_cost_usd,license_count\n" +
  "CrowdStrike Falcon,CrowdStrike,EDR,120000,500\n" +
  "Splunk Enterprise,Splunk,SIEM,200000,100\n" +
  "Okta,Okta,IAM,60000,500\n" +
  "Tenable Nessus,Tenable,VulnScan,40000,50\n";

test("tech-debt extract builds the dashboard, and editing a cell clears the AI-confidence badge", async ({
  page,
}) => {
  // Upload + extraction + auto-save PATCH against a next-dev server that is
  // also serving the other smoke specs; requests can queue for tens of
  // seconds, so triple the budget.
  test.slow();
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  // Resolve the seeded Atlas Tech Debt service at runtime (scripts/seed_demo.py).
  const techDebtServiceId = await atlasServiceId(page, "tech_debt");
  await page.goto(`/admin/services/${techDebtServiceId}/tech-debt`);

  // EnsureActiveClient aligns the active tenant to Atlas before the workspace
  // renders its header — and it must render before the API calls below so the
  // active-client cookie is set and the proxy requests are tenant-scoped.
  await expect(
    page.getByRole("heading", { name: "Tech Debt Review" }),
  ).toBeVisible({ timeout: 30000 });

  // Discard any open draft first. Sprint 8 T1 (tech_debt.py:184) added a
  // draft-exists guard: a POST to /extract while a DRAFT is open REUSES that
  // draft (idempotent 200) instead of minting a new version, so a plain upload
  // would hand back a previous run's already-curated draft and the "AI 60%" row
  // would be gone. Discarding throws the open DRAFT away (Sprint 9 T0 / D-031;
  // _latest_ skips DISCARDED, so GET latest falls back to the seeded RELEASED
  // version and the upload below cuts a genuinely fresh draft) — this retires
  // the old approve-first dance.
  const prior = await page.request.get(
    `/api/proxy/tech-debt/services/${techDebtServiceId}/capability-lists/latest`,
  );
  if (prior.ok()) {
    const p = (await prior.json()) as { id: string; status: string };
    if (p.status === "draft") {
      const discarded = await page.request.post(
        `/api/proxy/tech-debt/capability-lists/${p.id}/discard`,
      );
      expect(discarded.ok()).toBeTruthy();
    }
  }

  // Upload the inventory via the hidden Dropzone file input. The upload triggers
  // a fixture-mode extraction that mints a fresh draft capability list.
  const extractDone = page.waitForResponse(
    (r) =>
      r.url().includes("/capability-lists/extract") &&
      r.request().method() === "POST",
    { timeout: 120000 },
  );
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "inventory.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(INVENTORY_CSV),
    });
  await extractDone;

  // The extraction produced a fresh editable draft (never "Released vN").
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });

  // Dashboard NumberCards summarize the extracted list.
  await expect(page.getByText("Capabilities", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText("Annual cost", { exact: true })).toBeVisible();
  await expect(page.getByText("Categories", { exact: true })).toBeVisible();
  await expect(page.getByText("To consolidate / cut")).toBeVisible();
  // exact: the "N low-confidence rows" StatusPill would otherwise also match.
  await expect(
    page.getByText("Low-confidence rows", { exact: true }),
  ).toBeVisible();

  // Exactly one extracted row is stamped "AI 60%". Editing any cell in that row
  // must clear the AI badge and re-label the row "Human-curated".
  const aiBadge = page.getByText("AI 60%", { exact: true });
  await expect(aiBadge).toBeVisible({ timeout: 30000 });

  const editRow = page.locator("tr", {
    has: page.getByText("AI 60%", { exact: true }),
  });
  const patchDone = page.waitForResponse(
    (r) =>
      r.url().includes("/tech-debt/capability-items/") &&
      r.request().method() === "PATCH" &&
      r.ok(),
    { timeout: 90000 },
  );
  const nameCell = editRow.getByLabel("Name");
  await nameCell.fill("CrowdStrike Falcon (curated)");
  await nameCell.blur();
  await patchDone;

  // The AI-authored badge is gone, replaced by a human-curated one on that row.
  await expect(page.getByText("AI 60%", { exact: true })).toHaveCount(0, {
    timeout: 15000,
  });
  await expect(page.getByText("Human-curated").first()).toBeVisible();
});

test("Discard draft throws the open draft away and re-enables a fresh extraction (SMOKE §31)", async ({
  page,
}) => {
  // The browser proof for SMOKE §31 (Sprint 9 T1/T3): the discard affordance
  // driven through the app's first destructive-confirm Modal. Tech-debt is the
  // service that proves "fresh mint follows" through the UI — its upload card is
  // always present, so after discard a re-upload extracts a brand-new draft.
  test.slow();
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  const techDebtServiceId = await atlasServiceId(page, "tech_debt");
  await page.goto(`/admin/services/${techDebtServiceId}/tech-debt`);
  await expect(
    page.getByRole("heading", { name: "Tech Debt Review" }),
  ).toBeVisible({ timeout: 30000 });

  // Discard any stale open draft, then upload to mint a fresh draft we can throw
  // away through the UI below.
  const prior = await page.request.get(
    `/api/proxy/tech-debt/services/${techDebtServiceId}/capability-lists/latest`,
  );
  if (prior.ok()) {
    const p = (await prior.json()) as { id: string; status: string };
    if (p.status === "draft") {
      const discarded = await page.request.post(
        `/api/proxy/tech-debt/capability-lists/${p.id}/discard`,
      );
      expect(discarded.ok()).toBeTruthy();
    }
  }

  const firstExtract = page.waitForResponse(
    (r) =>
      r.url().includes("/capability-lists/extract") &&
      r.request().method() === "POST",
    { timeout: 120000 },
  );
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "inventory.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(INVENTORY_CSV),
    });
  await firstExtract;
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });

  // Cancel is a no-op: open the Modal, dismiss it, the draft survives intact.
  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(
    page.getByRole("heading", { name: "Discard this draft?" }),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText(/Draft v\d+/)).toBeVisible();

  // Confirm the discard: the draft is thrown away.
  const discardDone = page.waitForResponse(
    (r) =>
      r.url().includes("/capability-lists/") &&
      r.url().includes("/discard") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 60000 },
  );
  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(
    page.getByRole("heading", { name: "Discard this draft?" }),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Yes, discard" }).click();
  await discardDone;

  // The draft is gone: its Draft pill and the Discard affordance both disappear
  // (the list falls back to the prior approved/released version, read-only), and
  // the always-present upload card keeps a fresh extraction live.
  await expect(page.getByText(/Draft v\d+/)).toHaveCount(0, { timeout: 30000 });
  await expect(page.getByRole("button", { name: "Discard draft" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("heading", { name: "Upload inventory and extract" }),
  ).toBeVisible();

  // A fresh mint follows: re-uploading extracts a brand-new draft.
  const secondExtract = page.waitForResponse(
    (r) =>
      r.url().includes("/capability-lists/extract") &&
      r.request().method() === "POST",
    { timeout: 120000 },
  );
  await page
    .locator('input[type="file"]')
    .first()
    .setInputFiles({
      name: "inventory.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(INVENTORY_CSV),
    });
  await secondExtract;
  await expect(page.getByText(/Draft v\d+/)).toBeVisible({ timeout: 30000 });
});
