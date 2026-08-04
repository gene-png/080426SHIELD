import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, signIn } from "../helpers/auth";
import { atlasClientId, atlasServiceId } from "../helpers/ids";

/**
 * SMOKE_TEST.md section 8 (T7): the Risk Register (Work Order E).
 *
 *   1. Gate: a client with ONLY an ATT&CK assessment sees the locked state
 *      listing what's missing; adding a CSF or ZT assessment unlocks it.
 *      (Tested on a throwaway tenant so the shared Atlas data can't mask it.)
 *   2. Generate on Atlas: entries appear and every tier is CODE-derived from
 *      likelihood x impact (incl. the known combo High x Catastrophic =
 *      Critical); KPI cards + the 5x5 heatmap render; cited technique links
 *      only reference the client's own ATT&CK assessment.
 *   3. Regenerate bumps the version.
 *   4. Export streams XLSX/PDF/Word (HTTP 200 + content-type), saved to
 *      e2e/artifacts/ for David's section-10 eyeball.
 */

const ARTIFACTS_DIR = path.resolve(__dirname, "..", "artifacts");

// --- Client-side mirror of app/risk/engine.py tier_for (NIST 800-30 5x5) ----
const LIKELIHOODS = ["very_low", "low", "medium", "high", "very_high"];
const IMPACTS = ["negligible", "minor", "moderate", "major", "catastrophic"];

function tierFor(l: string, i: string): string {
  const li = LIKELIHOODS.indexOf(l);
  const ii = IMPACTS.indexOf(i);
  if ((l === "high" || l === "very_high") && i === "catastrophic")
    return "critical";
  if (l === "very_high" && ii >= IMPACTS.indexOf("major")) return "critical";
  const s = (li + 1) * (ii + 1);
  if (s >= 15) return "high";
  if (s >= 9) return "medium";
  if (s >= 4) return "low";
  return "negligible";
}

interface RiskEntry {
  likelihood: string | null;
  impact: string | null;
  tier: string | null;
  linked_techniques: string[];
}

interface RiskRegisterResponse {
  version: number;
  entries: RiskEntry[];
  xlsx_artifact_id: string | null;
  pdf_artifact_id: string | null;
  docx_artifact_id: string | null;
  xlsx_filename: string | null;
  pdf_filename: string | null;
  docx_filename: string | null;
}

/** Point the admin's client switcher at `clientId` via the cookie route. */
async function setActiveClient(page: Page, clientId: string): Promise<void> {
  const res = await page.request.post("/api/active-client", {
    data: { clientId },
  });
  expect(res.ok()).toBeTruthy();
}

test("seeded Atlas Risk Register renders code-derived tiers and its exports download (T8 demo seed)", async ({
  page,
}) => {
  test.slow();
  // Sprint 6 T8: the demo seed now synthesizes a Risk Register for Atlas (4
  // services + a register, all released + downloadable) so the demo journey is
  // coherent out of the box. This is READ-ONLY (no generate/regenerate) so it
  // never perturbs the shared register version the other tests delta-assert.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  const atlasClientIdValue = await atlasClientId(page);
  await setActiveClient(page, atlasClientIdValue);

  await page.goto("/admin/risk-register");
  await expect(
    page.getByRole("heading", { name: "Risk Register", exact: true }),
  ).toBeVisible({ timeout: 60000 });

  // A register already exists (the seed's contribution — before T8 a fresh seed
  // had none until a test generated one).
  const latest = await page.request.get(
    `/api/proxy/risk/clients/${atlasClientIdValue}/register/latest`,
  );
  expect(latest.ok(), "seeded register exists on latest").toBeTruthy();
  const register = (await latest.json()) as RiskRegisterResponse;
  expect(register.entries.length).toBeGreaterThan(0);

  // Tier is ALWAYS code-derived from likelihood x impact (the seed runs the same
  // engine, never hard-coded tiers).
  for (const e of register.entries) {
    if (e.likelihood && e.impact) {
      expect(e.tier, `${e.likelihood} x ${e.impact}`).toBe(
        tierFor(e.likelihood, e.impact),
      );
    }
  }

  // The register's exports (XLSX/PDF/Word) are present and download (200 with a
  // §15.5 filename) — the "downloadable reports" half of the demo story.
  const exports: Array<{
    id: string | null;
    filename: string | null;
    contentType: string;
    ext: string;
  }> = [
    {
      id: register.xlsx_artifact_id,
      filename: register.xlsx_filename,
      contentType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      ext: "xlsx",
    },
    {
      id: register.pdf_artifact_id,
      filename: register.pdf_filename,
      contentType: "application/pdf",
      ext: "pdf",
    },
    {
      id: register.docx_artifact_id,
      filename: register.docx_filename,
      contentType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ext: "docx",
    },
  ];
  for (const dl of exports) {
    expect(dl.id, `${dl.ext} artifact id`).toBeTruthy();
    expect(dl.filename ?? "", `${dl.ext} §15.5 name`).toMatch(
      new RegExp(`^[A-Za-z0-9_]+_Risk_Register\\d{6}(_v\\d+)?\\.${dl.ext}$`),
    );
    const res = await page.request.get(
      `/api/proxy/artifacts/${dl.id}/download`,
    );
    expect(res.status(), `${dl.ext} download status`).toBe(200);
    expect(res.headers()["content-type"], `${dl.ext} content-type`).toContain(
      dl.contentType,
    );
    const body = await res.body();
    expect(body.length, `${dl.ext} byte size`).toBeGreaterThan(0);
  }
});

test("register is locked with only ATT&CK and unlocks once a ZT assessment exists", async ({
  page,
}) => {
  test.slow();
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);

  // Throwaway tenant so seeded Atlas assessments can't satisfy the gate.
  const createdClient = await page.request.post("/api/proxy/admin/clients", {
    data: { legal_name: `QA Risk Gate ${Date.now()}` },
  });
  expect(createdClient.ok()).toBeTruthy();
  const clientId = ((await createdClient.json()) as { id: string }).id;
  await setActiveClient(page, clientId);

  // Give the tenant ONLY an ATT&CK coverage assessment.
  const attackSvc = await page.request.post("/api/proxy/attack/services", {
    data: { kind: "attack_coverage", title: "QA ATT&CK Coverage" },
  });
  expect(attackSvc.ok()).toBeTruthy();
  const attackSvcId = ((await attackSvc.json()) as { id: string }).id;
  const attackAssessment = await page.request.post(
    `/api/proxy/attack/services/${attackSvcId}/assessments`,
  );
  expect(attackAssessment.ok()).toBeTruthy();

  // Locked: the empty state names exactly what's missing, and there is no
  // Generate button.
  await page.goto("/admin/risk-register");
  await expect(page.getByText("Risk Register is locked")).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText(/a CSF or Zero Trust assessment/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Generate|Regenerate/ }),
  ).toHaveCount(0);

  // Add a Zero Trust (CISA) assessment -> the gate unlocks on reload.
  const ztSvc = await page.request.post("/api/proxy/zt/services", {
    data: { kind: "zero_trust_cisa", title: "QA Zero Trust (CISA)" },
  });
  expect(ztSvc.ok()).toBeTruthy();
  const ztSvcId = ((await ztSvc.json()) as { id: string }).id;
  const ztAssessment = await page.request.post(
    `/api/proxy/zt/services/${ztSvcId}/assessments`,
  );
  expect(ztAssessment.ok()).toBeTruthy();

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Risk Register", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("Risk Register is locked")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Generate" })).toBeVisible();
});

test("Generate derives tiers in code, renders KPIs + 5x5 heatmap, cites only the client's own techniques; Regenerate bumps version; exports download", async ({
  page,
}) => {
  test.slow();
  test.setTimeout(300_000);
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  // Seeded Atlas Defense tenant + its ATT&CK service (scripts/seed_demo.py).
  const atlasClientIdValue = await atlasClientId(page);
  const atlasAttackServiceId = await atlasServiceId(page, "attack_coverage");
  await setActiveClient(page, atlasClientIdValue);

  await page.goto("/admin/risk-register");
  await expect(
    page.getByRole("heading", { name: "Risk Register", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);

  // Version assertions are delta-based: the shared DB may already hold a
  // register from earlier runs.
  const latest = await page.request.get(
    `/api/proxy/risk/clients/${atlasClientIdValue}/register/latest`,
  );
  const priorVersion = latest.ok()
    ? ((await latest.json()) as RiskRegisterResponse).version
    : 0;

  // --- Generate --------------------------------------------------------------
  const generated = page.waitForResponse(
    (r) =>
      r.url().includes("/register/generate") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 120000 },
  );
  await page.getByRole("button", { name: /^(Generate|Regenerate)$/ }).click();
  const register = (await (await generated).json()) as RiskRegisterResponse;
  expect(register.version).toBe(priorVersion + 1);
  expect(register.entries.length).toBeGreaterThan(0);

  // Tier is ALWAYS code-derived from likelihood x impact (never AI-set):
  // every entry matches the engine's 5x5 mapping...
  for (const e of register.entries) {
    if (e.likelihood && e.impact) {
      expect(e.tier, `${e.likelihood} x ${e.impact}`).toBe(
        tierFor(e.likelihood, e.impact),
      );
    }
  }
  // ...including the known combo High x Catastrophic = Critical.
  const highCat = register.entries.filter(
    (e) => e.likelihood === "high" && e.impact === "catastrophic",
  );
  expect(highCat.length).toBeGreaterThan(0);
  for (const e of highCat) {
    expect(e.tier).toBe("critical");
  }

  // Cited technique links only reference the client's OWN ATT&CK assessment.
  const attackLatest = await page.request.get(
    `/api/proxy/attack/services/${atlasAttackServiceId}/assessments/latest`,
  );
  expect(attackLatest.ok()).toBeTruthy();
  const coverage = (
    (await attackLatest.json()) as {
      coverage: Array<{ technique_code: string }>;
    }
  ).coverage;
  const ownTechniques = new Set(coverage.map((c) => c.technique_code));
  for (const e of register.entries) {
    for (const t of e.linked_techniques) {
      expect(ownTechniques.has(t), `linked technique ${t}`).toBeTruthy();
    }
  }

  // --- KPI cards + 5x5 heatmap ------------------------------------------------
  await expect(
    page.locator("p", { hasText: `version ${register.version}` }).first(),
  ).toBeVisible({ timeout: 60000 });
  for (const label of [
    "Entries",
    "Critical + High",
    "Detection",
    "Prevention",
    "Response",
  ]) {
    // Scope to the KPI card's <p> label — bare getByText would also match the
    // register table's Axis cells (e.g. hundreds of "Detection" <td>s).
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    await expect(
      page.locator("p", { hasText: new RegExp(`^${escaped}$`) }).first(),
    ).toBeVisible();
  }
  // Heatmap axes: all 5 impact columns and 5 likelihood rows.
  for (const impact of [
    "Negligible",
    "Minor",
    "Moderate",
    "Major",
    "Catastrophic",
  ]) {
    await expect(
      page.getByRole("columnheader", { name: impact, exact: true }),
    ).toBeVisible();
  }
  // Likelihood row labels are tbody <th scope="row"> (T6), so Chromium's a11y
  // tree exposes them as rowheaders. `exact` keeps "High" from matching
  // "Very High".
  for (const likelihood of ["Very High", "High", "Medium", "Low", "Very Low"]) {
    await expect(
      page.getByRole("rowheader", { name: likelihood, exact: true }),
    ).toBeVisible();
  }
  // The High x Catastrophic cell counts exactly the entries that land there.
  await expect(page.locator('td[title="High × Catastrophic"]')).toHaveText(
    String(highCat.length),
  );

  // --- Regenerate bumps the version -------------------------------------------
  const regenerated = page.waitForResponse(
    (r) =>
      r.url().includes("/register/generate") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 120000 },
  );
  await page.getByRole("button", { name: "Regenerate" }).click();
  const register2 = (await (await regenerated).json()) as RiskRegisterResponse;
  expect(register2.version).toBe(register.version + 1);
  await expect(
    page.locator("p", { hasText: `version ${register2.version}` }).first(),
  ).toBeVisible({ timeout: 60000 });

  // --- Export XLSX / PDF / Word ------------------------------------------------
  const exported = page.waitForResponse(
    (r) =>
      r.url().includes("/register/export") &&
      r.request().method() === "POST" &&
      r.ok(),
    { timeout: 180000 },
  );
  await page.getByRole("button", { name: "Export XLSX / PDF / Word" }).click();
  const withArtifacts = (await (await exported).json()) as RiskRegisterResponse;

  const downloads: Array<{
    id: string | null;
    filename: string | null;
    contentType: string;
    label: string;
    ext: string;
  }> = [
    {
      id: withArtifacts.xlsx_artifact_id,
      filename: withArtifacts.xlsx_filename,
      contentType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      label: "XLSX",
      ext: "xlsx",
    },
    {
      id: withArtifacts.pdf_artifact_id,
      filename: withArtifacts.pdf_filename,
      contentType: "application/pdf",
      label: "PDF",
      ext: "pdf",
    },
    {
      id: withArtifacts.docx_artifact_id,
      filename: withArtifacts.docx_filename,
      contentType:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      label: "Word",
      ext: "docx",
    },
  ];

  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
  for (const dl of downloads) {
    expect(dl.id, `${dl.label} artifact id`).toBeTruthy();
    expect(dl.filename, `${dl.label} filename`).toBeTruthy();
    // Master Spec §15.5: {Company}_Risk_Register{MMDDYY}[_v{n}].{ext}
    // (T4 routed the export through deliverable_filename() — no more raw
    // Risk_Register_v{n}).
    expect(dl.filename, `${dl.label} §15.5 name`).toMatch(
      new RegExp(`^[A-Za-z0-9_]+_Risk_Register\\d{6}(_v\\d+)?\\.${dl.ext}$`),
    );
    // The dashboard renders the download link (accessible name includes the
    // filename, so match on the label prefix).
    await expect(
      page.getByRole("link", { name: new RegExp(`^${dl.label}`) }),
    ).toBeVisible({ timeout: 30000 });
    const res = await page.request.get(
      `/api/proxy/artifacts/${dl.id}/download`,
    );
    expect(res.status(), `${dl.label} download status`).toBe(200);
    expect(res.headers()["content-type"], `${dl.label} content-type`).toContain(
      dl.contentType,
    );
    const body = await res.body();
    expect(body.length, `${dl.label} byte size`).toBeGreaterThan(0);
    // Saved for David's manual section-10 review (dir is gitignored).
    fs.writeFileSync(path.join(ARTIFACTS_DIR, dl.filename!), body);
  }
});
