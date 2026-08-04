import { expect, test, type Page } from "@playwright/test";

import { register, uniqueEmail } from "../helpers/auth";

/**
 * SMOKE_TEST.md section 3 (T5): the client self-assessment flow.
 *
 * A fresh @atlas.example self-registrant (atlas.example is an approved client
 * domain, seeded by T2) starts an assessment from /assessments, which drops
 * them into /self-assessment/[serviceId]?type=... (the bare /self-assessment
 * path 404s). We assert the spec's four contract points:
 *   1. Terminology: these surfaces say "assessment", never "engagement".
 *   2. CSF answers auto-save and persist across a save-and-exit + reopen.
 *   3. Submitting a CSF self-assessment moves its status to submitted.
 *   4. DoD ZTRA maturity scale shows exactly 3 levels (A4) — the DoD ladder is
 *      Not Started / Target / Advanced, versus CISA's 4.
 */

const PASSWORD = "correct horse battery staple!";

/** Register a throwaway Atlas client and confirm we land authenticated. */
async function registerAtlasClient(page: Page): Promise<string> {
  const email = uniqueEmail("atlas.example");
  await register(page, "Atlas Self-Assessment Tester", email, PASSWORD);
  // On success register() hard-navigates to /intake; the header shows Sign out.
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
    timeout: 20000,
  });
  return email;
}

/**
 * Start a new assessment from /assessments and wait until we land on the
 * self-assessment workspace. CSF needs a target tier + impact profile; ZT needs
 * a target stage. Returns the workspace URL so callers can reopen the EXACT
 * assessment they created (the tenant-scoped list accumulates drafts across
 * runs, so "first Continue link" is not guaranteed to be ours).
 */
async function startAssessment(
  page: Page,
  opts: {
    type: "nist_csf" | "zero_trust_cisa" | "zero_trust_dod";
    tier?: number;
    profile?: "LOW" | "MOD" | "HIGH";
    stage?: number;
  },
): Promise<string> {
  await page.goto("/assessments");
  await expect(
    page.getByRole("heading", { name: "My assessments" }),
  ).toBeVisible({ timeout: 20000 });
  await page.getByRole("button", { name: "+ Start a new assessment" }).click();
  await page
    .getByRole("combobox", { name: "Assessment type" })
    .selectOption(opts.type);
  if (opts.type === "nist_csf") {
    await page
      .getByRole("combobox", { name: "Target tier" })
      .selectOption(String(opts.tier));
    await page
      .getByRole("combobox", { name: "Impact profile" })
      .selectOption(opts.profile ?? "LOW");
  } else {
    await page
      .getByRole("combobox", { name: "Target stage" })
      .selectOption(String(opts.stage));
  }
  await page.getByRole("button", { name: "Start assessment" }).click();
  await page.waitForURL(/\/self-assessment\//, { timeout: 30000 });
  return page.url();
}

test("self-assessment surfaces use 'assessment' terminology, never 'engagement'", async ({
  page,
}) => {
  await registerAtlasClient(page);

  await page.goto("/assessments");
  await expect(
    page.getByRole("heading", { name: "My assessments" }),
  ).toBeVisible({ timeout: 20000 });
  const listText = (
    await page.locator("#main-content").innerText()
  ).toLowerCase();
  expect(listText).toContain("assessment");
  expect(listText).not.toContain("engagement");

  // A1: a freshly-registered client sees NO admin/deliverables links anywhere
  // on the client shell (nav + page body).
  await expect(
    page.getByRole("link", { name: /admin|deliverable/i }),
  ).toHaveCount(0);

  // And the self-assessment workspace itself.
  await startAssessment(page, { type: "nist_csf", tier: 3, profile: "LOW" });
  await expect(
    page.getByRole("heading", { name: /self-assessment/i }),
  ).toBeVisible({ timeout: 30000 });
  const workspaceText = (await page.locator("main").innerText()).toLowerCase();
  expect(workspaceText).toContain("assessment");
  expect(workspaceText).not.toContain("engagement");
});

test("CSF answers persist across save-and-exit, and submit moves the status", async ({
  page,
}) => {
  await registerAtlasClient(page);
  const workspaceUrl = await startAssessment(page, {
    type: "nist_csf",
    tier: 3,
    profile: "LOW",
  });
  // The path segment after /self-assessment/ identifies OUR assessment's
  // service; used below to reopen the exact draft we answered.
  const serviceId = new URL(workspaceUrl).pathname.split("/").pop() as string;

  await expect(
    page.getByRole("heading", { name: "CSF 2.0 questionnaire" }),
  ).toBeVisible({ timeout: 30000 });

  // Answer 2-3 outcomes in the default (first) function tab. Each TierPicker is
  // a radiogroup labelled "Maturity tier for <code>"; picking a tier auto-saves
  // via PATCH .../csf/self-assessment/answers/<id>.
  const groups = page.getByRole("radiogroup");
  const groupCount = await groups.count();
  expect(groupCount).toBeGreaterThanOrEqual(2);
  const toAnswer = Math.min(3, groupCount);

  const chosen: Array<{ label: string; tierIdx: number }> = [];
  for (let i = 0; i < toAnswer; i++) {
    const group = groups.nth(i);
    const label = await group.getAttribute("aria-label");
    expect(label).toBeTruthy();
    const tierIdx = i % 4; // 0..2 -> T1..T3
    const saved = page.waitForResponse(
      (r) =>
        r.url().includes("/csf/self-assessment/answers/") &&
        r.request().method() === "PATCH" &&
        r.ok(),
    );
    await group.getByRole("radio").nth(tierIdx).click();
    await saved;
    chosen.push({ label: label as string, tierIdx });
  }

  // Save-and-exit: navigate away, then reopen via OUR assessment's Continue
  // link (matched by service id — the tenant-scoped list accumulates drafts
  // across runs, so a bare .first() could open somebody else's draft).
  await page.goto("/assessments");
  await expect(
    page.getByRole("heading", { name: "My assessments" }),
  ).toBeVisible({ timeout: 20000 });
  await page
    .locator(`a[href*="${serviceId}"]`)
    .filter({ hasText: /Continue/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "CSF 2.0 questionnaire" }),
  ).toBeVisible({ timeout: 30000 });

  // The tiers we picked are still selected after the round-trip.
  for (const { label, tierIdx } of chosen) {
    const group = page.getByRole("radiogroup", { name: label });
    await expect(group.getByRole("radio").nth(tierIdx)).toHaveAttribute(
      "aria-checked",
      "true",
    );
  }

  // Submit for review moves the assessment out of draft.
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByText("Self-assessment submitted")).toBeVisible({
    timeout: 20000,
  });

  // Back on the tenant-scoped list, at least one assessment now reads
  // "Submitted — under review". The list is scoped to the Atlas client (not the
  // individual user), so prior spec runs in the shared seeded DB can leave more
  // than one submitted pill; our own submission was already proven by the
  // confirmation card above, so .first() keeps this robust against accumulation.
  await page.goto("/assessments");
  await expect(page.getByText(/submitted.*under review/i).first()).toBeVisible({
    timeout: 20000,
  });
});

/**
 * SMOKE_TEST.md section 3, C8: the rendered CSF questionnaire prompts must be
 * the VERBATIM subcategory outcome statements, not a paraphrase or a truncated
 * label. Each question card renders `subcategory.outcome` (the "outcome
 * statement assessors score against") beneath the short name.
 *
 * Source of record for the verbatim text: apps/api/app/csf/catalog.py
 * SUBCATEGORIES — the deterministic CSF catalog the questionnaire renders from
 * ("AI suggests, code computes"), transcribing the canonical NIST CSF 2.0
 * Final (Feb 2024) outcome statements. The master spec
 * (reference-docs/SHIELDv2_Master_Spec.txt §7, ~line 1413) defines the
 * subcategory model (GV.OC-01, GV.OC-02, …) but not the per-item outcome text,
 * so catalog.py is the authoritative verbatim source. This test asserts the
 * DOM text equals these literals exactly, guarding against UI truncation /
 * reformatting or catalog drift.
 *
 * GV.OC-* are chosen because GOVERN is the default (first) function tab and
 * GV.OC (Organizational Context) is in scope at every impact profile,
 * including LOW — so all three render on initial load with no tab switching.
 */
const CSF_VERBATIM_PROMPTS: Record<string, string> = {
  "GV.OC-01":
    "The organizational mission is understood and informs cybersecurity risk management.",
  "GV.OC-02":
    "Internal and external stakeholders are understood, and their needs and expectations regarding cybersecurity are considered.",
  "GV.OC-03":
    "Legal, regulatory, and contractual requirements regarding cybersecurity are understood and managed.",
};

test("CSF questionnaire renders the verbatim subcategory outcome prompts (C8)", async ({
  page,
}) => {
  await registerAtlasClient(page);
  await startAssessment(page, { type: "nist_csf", tier: 3, profile: "LOW" });

  await expect(
    page.getByRole("heading", { name: "CSF 2.0 questionnaire" }),
  ).toBeVisible({ timeout: 30000 });

  // GOVERN is the default tab; assert each GV.OC prompt renders VERBATIM.
  for (const [code, prompt] of Object.entries(CSF_VERBATIM_PROMPTS)) {
    // The subcategory code label anchors us to the right card.
    await expect(page.getByText(code, { exact: true }).first()).toBeVisible({
      timeout: 30000,
    });
    // Exact-match the outcome text so a paraphrase or truncation would fail.
    await expect(page.getByText(prompt, { exact: true }).first()).toBeVisible();
  }
});

test("DoD Zero Trust self-assessment maturity scale shows exactly 3 levels", async ({
  page,
}) => {
  await registerAtlasClient(page);
  await startAssessment(page, { type: "zero_trust_dod", stage: 2 });

  // The DoD workspace loads the ZTRA self-assessment.
  await expect(page.getByRole("heading", { name: /DoD ZTRA/i })).toBeVisible({
    timeout: 30000,
  });

  // Each capability's maturity picker is a radiogroup ("Maturity stage for
  // <code>"). For DoD ZTRA the ladder is exactly 3 stages (Not Started /
  // Target / Advanced) — CISA would show 4.
  const stagePicker = page
    .getByRole("radiogroup", { name: /Maturity stage for/i })
    .first();
  await expect(stagePicker).toBeVisible({ timeout: 30000 });
  await expect(stagePicker.getByRole("radio")).toHaveCount(3);
});
