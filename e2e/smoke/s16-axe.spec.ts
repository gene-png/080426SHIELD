import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  register,
  signIn,
  uniqueEmail,
} from "../helpers/auth";
import { atlasServiceId } from "../helpers/ids";

/**
 * SMOKE_TEST.md accessibility sweep (SPRINT_2 T4): a runtime axe-core pass over
 * the app's primary public, client, and admin surfaces. Fails on any WCAG 2.0/2.1
 * Level A or AA violation, so a11y regressions cannot merge silently — the sweep
 * runs in the same serialized suite T3's CI job executes.
 *
 * Surfaces (per T4):
 *   - signed out: home, /sign-in, /sign-up
 *   - client:     /assessments + one CSF self-assessment questionnaire
 *   - admin:      /admin/queue (dashboard) + one CSF service workspace
 *
 * Scope note on the risk heatmap: the known `scope="row"` gap on the risk-register
 * heatmap (tbody <th> likelihood labels not resolving as rowheaders) is fixed in
 * T6, not here. That heatmap lives on the risk-register surfaces, which are outside
 * this sweep's enumerated seven surfaces; none of the surfaces below render it, so
 * no rule exclusion is required. If a future revision adds a risk-register surface
 * to this sweep before T6 lands, disable ONLY the offending rule here with a
 * comment pointing at T6 rather than weakening the WCAG tag set.
 */

const PASSWORD = "correct horse battery staple!";

/** WCAG 2.0 + 2.1, Levels A and AA — the conformance target for SHIELD. */
const WCAG_AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/**
 * Deliberately-disabled rules, each with a justification. Empty today: every
 * finding on the swept surfaces is either clean or fixed inline. Add entries
 * ONLY with an inline reason and a follow-up reference (e.g. a task id).
 */
const DISABLED_RULES: string[] = [];

interface AxeViolationNode {
  target: string[];
  html: string;
}
interface AxeViolation {
  id: string;
  impact?: string | null;
  help: string;
  helpUrl: string;
  nodes: AxeViolationNode[];
}

/** Run axe on the current page for the WCAG A/AA tag set. */
async function analyze(page: Page): Promise<AxeViolation[]> {
  const builder = new AxeBuilder({ page }).withTags(WCAG_AA_TAGS);
  if (DISABLED_RULES.length > 0) builder.disableRules(DISABLED_RULES);
  const results = await builder.analyze();
  return results.violations as AxeViolation[];
}

/** Human-readable failure summary so triage needs no trace opening. */
function summarize(surface: string, violations: AxeViolation[]): string {
  if (violations.length === 0) return `${surface}: no WCAG A/AA violations`;
  const lines = violations.map((v) => {
    const targets = v.nodes
      .slice(0, 4)
      .map((n) => n.target.join(" "))
      .join(", ");
    return `  - ${v.id} (${v.impact ?? "n/a"}) x${v.nodes.length}: ${v.help}\n      at: ${targets}\n      ${v.helpUrl}`;
  });
  return `${surface}: ${violations.length} WCAG A/AA violation(s):\n${lines.join("\n")}`;
}

/** Assert a surface is clean, printing full detail on failure. */
async function expectClean(page: Page, surface: string): Promise<void> {
  const violations = await analyze(page);
  if (violations.length > 0) {
    // Surfaces the full detail in the reporter output for triage.
    console.error(summarize(surface, violations));
  }
  expect(violations, summarize(surface, violations)).toEqual([]);
}

test.describe("axe: signed-out public surfaces", () => {
  test("home has no WCAG A/AA violations", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("link", { name: /SHIELD/ }).first(),
    ).toBeVisible();
    await expectClean(page, "home (/)");
  });

  test("sign-in has no WCAG A/AA violations", async ({ page }) => {
    await page.goto("/sign-in");
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expectClean(page, "/sign-in");
  });

  test("sign-up has no WCAG A/AA violations", async ({ page }) => {
    await page.goto("/sign-up");
    await expect(page.locator("#display_name")).toBeVisible();
    await expectClean(page, "/sign-up");
  });
});

test.describe("axe: client surfaces", () => {
  test("assessments list + CSF questionnaire have no WCAG A/AA violations", async ({
    page,
  }) => {
    test.slow();
    // A fresh @atlas.example self-registrant (approved domain, seeded by T2) so
    // the questionnaire renders live maturity controls, not an empty state.
    await register(
      page,
      "Axe Sweep Tester",
      uniqueEmail("atlas.example"),
      PASSWORD,
    );
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible({
      timeout: 20000,
    });

    await page.goto("/assessments");
    await expect(
      page.getByRole("heading", { name: "My assessments" }),
    ).toBeVisible({ timeout: 20000 });
    await expectClean(page, "/assessments");

    // Start a CSF self-assessment -> the questionnaire workspace.
    await page
      .getByRole("button", { name: "+ Start a new assessment" })
      .click();
    await page
      .getByRole("combobox", { name: "Assessment type" })
      .selectOption("nist_csf");
    await page.getByRole("combobox", { name: "Target tier" }).selectOption("3");
    await page
      .getByRole("combobox", { name: "Impact profile" })
      .selectOption("LOW");
    await page.getByRole("button", { name: "Start assessment" }).click();
    await page.waitForURL(/\/self-assessment\//, { timeout: 30000 });
    await expect(
      page.getByRole("heading", { name: "CSF 2.0 questionnaire" }),
    ).toBeVisible({ timeout: 30000 });
    // Ensure the maturity controls have rendered before scanning.
    await expect(page.getByRole("radiogroup").first()).toBeVisible({
      timeout: 30000,
    });
    await expectClean(page, "CSF self-assessment questionnaire");
  });
});

test.describe("axe: admin surfaces", () => {
  test("admin dashboard + CSF workspace have no WCAG A/AA violations", async ({
    page,
  }) => {
    test.slow();
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

    // Admin dashboard: the intake queue is the admin landing surface.
    await page.goto("/admin/queue");
    await expect(
      page.getByRole("navigation", { name: "Primary" }).first(),
    ).toBeVisible({ timeout: 20000 });
    await expectClean(page, "/admin/queue");

    // One workspace: the seeded Atlas "NIST CSF 2.0" service assessment.
    const csfServiceId = await atlasServiceId(page, "nist_csf");
    await page.goto(`/admin/services/${csfServiceId}/csf`);
    await expect(
      page.getByRole("heading", { name: "NIST CSF 2.0 Assessment" }),
    ).toBeVisible({ timeout: 30000 });
    // Wait for the latest-assessment fetch to resolve (status pill) so the scan
    // runs against the populated workspace, not a loading skeleton.
    await expect(
      page
        .getByText(/(Draft|Submitted|Approved|Released) v\d+|No assessment yet/)
        .first(),
    ).toBeVisible({ timeout: 30000 });
    await expectClean(page, "admin CSF workspace");
  });
});
