import fs from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import {
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
  register,
  signIn,
  signOut,
} from "../helpers/auth";
import { acknowledgeOfflineAi } from "../helpers/ai";

/**
 * FULL-ENGAGEMENT DEMO RUN — an OBSERVATION INSTRUMENT, not a gate.
 *
 * =========================================================================
 * WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT (read before changing it)
 * =========================================================================
 *
 * This spec walks one client engagement end to end — register, intake, four
 * service workspaces plus the Risk Register, generate and release every
 * deliverable, then cross into the CLIENT view and back to admin — and RECORDS
 * what it saw. It asserts NOTHING about content: no numbers, no counts, no
 * `toHaveCount`, no copy matching.
 *
 * That is deliberate and it is the whole point. Gene needs to see the real
 * current state of the product, not a run that aborted on the first wrong
 * number. A spec that fails at step 4 records nothing about steps 5 through 40,
 * and the steps it never reached are exactly the ones nobody has looked at.
 *
 * **There is no `expect` in this file at all**, and that is checkable in one
 * grep rather than taken on trust. Waiting is done with `locator.waitFor` via
 * the `affordance()` helper, which converts a timeout into a recorded
 * `unreachable` observation instead of a failure — so a screen that never
 * rendered is logged and the run CONTINUES to the next service. `helpers/auth`
 * and `helpers/ai` do assert internally; a throw from either surfaces as a
 * recorded `failed` step, never as an aborted run.
 *
 * **Current status: nothing here is a contract yet.** Once Gene has watched the
 * video and read the step log, we decide together which observations become
 * assertions. Until that conversation happens, adding an assertion to this file
 * converts an instrument into a gate that nobody agreed to.
 *
 * ---
 *
 * ## Three outputs
 *
 * 1. **Video** (`test.use({ video: "on" })`) — the whole flow, one continuous
 *    recording, because the whole flow is ONE test sharing ONE browser context.
 * 2. **Trace** (`test.use({ trace: "on" })`) — a DOM snapshot per action plus
 *    the network calls behind each screen, so when a number looks wrong you can
 *    tell whether the API or the renderer produced it.
 * 3. **Every generated artifact**, downloaded into a dated folder under
 *    `e2e/artifacts/`, named by SERVICE and CLIENT. A video shows the click that
 *    produced a deliverable; it does not show what is inside it.
 *
 * Video and trace are set HERE at the spec level, never in
 * `e2e/playwright.config.ts`. Verified against that file: it sets
 * `trace: "on-first-retry"` and no video at all, so turning either on globally
 * would slow every existing spec and change CI's E2E job. `test.use` overrides
 * the project `use` block for this file only.
 *
 * ## Why the admin -> client -> admin crossings are in ONE test
 *
 * The defects this exists to catch are two surfaces disagreeing about one
 * assessment (#114, #207 — "the document and the dashboard disagree"). Two
 * independent logins in sequence would skip the transition itself. So this is a
 * single test on a single `page`: the admin signs OUT through the header
 * control, the client signs IN on the same page, and later the admin signs back
 * in on that same page. The crossings genuinely happen in the browser, and they
 * land in the middle of one video rather than being split across three.
 *
 * ## Operating constraints (`e2e/globalSetup.ts` / `globalTeardown.ts`)
 *
 * There is a container-identity guard around every run. The run FAILS AT
 * TEARDOWN if `apps/api` is edited or any container is recreated while it is in
 * flight — `uvicorn --reload` takes an API edit mid-run while `apps/web` keeps
 * serving the old build, so an edited-under stack silently tests a combination
 * that exists nowhere. This spec is long (budget below), which widens that
 * window considerably. **Do not edit `apps/api`, do not `docker compose up` or
 * `restart` anything, and do not run another Playwright process while this is
 * running.**
 *
 * Also inherited from `playwright.config.ts`: `workers: 1`, serialized,
 * chromium, `baseURL` http://localhost:3000. `SHIELD_LLM_MODE` is `fixture`, so
 * every Run-AI here is deterministic and offline and no provider key is needed —
 * which also means the offline Run-AI guard dialog appears and is acknowledged
 * (helpers/ai.ts).
 *
 * ## Why it is opt-in, and why that is not the "spec that self-skips" defect
 *
 * `playwright.config.ts` sets `testDir: "."` with no `testIgnore`, and CI's E2E
 * job runs a bare `npx playwright test` from `e2e/` (`.github/workflows/ci.yml`,
 * job `e2e`, step "Run Playwright suite"). So a new spec anywhere under `e2e/`
 * joins CI by default. This file is therefore gated on `SHIELD_FULL_ENGAGEMENT`
 * — the same opt-in shape `demo/demo-journey.spec.ts` uses for
 * `SHIELD_DEMO_SMOKE` (D-033), `perf-admin-management.spec.ts` for `E2E_PERF`,
 * and `s26-oidc-login` for `E2E_OIDC`. With the flag unset the file is collected
 * and reported as SKIPPED: it executes no steps, and it cannot turn CI red or
 * green.
 *
 * CLAUDE.md records that "a spec that self-skips on a data precondition is
 * UNTESTED, not passing" (`s34`). This is not that. That rule is about a spec
 * branching on SEEDED DATA it does not control, so whether it ever exercised its
 * subject depended on shared database state — a skip that hid a real fail-open
 * defect. This gate is an explicit operator switch on an instrument that asserts
 * nothing: there is no contract for the skip to silently stop proving. It also
 * seeds every precondition it needs (a brand-new tenant per run) rather than
 * branching on what happens to be in the database, which is the remedy that rule
 * actually prescribes.
 *
 * ## Run it
 *
 * GIT BASH form. NOT RUN in any shell by the author — this spec was authored
 * and checked (prettier, tsc --strict) but deliberately never executed, because
 * host-run Playwright drives the shared Docker stack and execution is being
 * coordinated separately. Treat both blocks below as unverified until someone
 * runs them.
 *
 *   cd e2e
 *   SHIELD_FULL_ENGAGEMENT=1 npx playwright test engagement/
 *
 * The two lines are separate on purpose: `cd e2e && npx playwright test` is the
 * one command in CLAUDE.md's "Real commands" section that carries an OUTER `&&`
 * between two host commands, which is a parse error in PowerShell 5.1.
 *
 * PowerShell 5.1 equivalent — also UNVERIFIED, and offered because this repo is
 * developed on Windows where PowerShell is the default shell. `VAR=x cmd` has no
 * PowerShell equivalent, so the variable is set as its own statement:
 *
 *   cd e2e
 *   $env:SHIELD_FULL_ENGAGEMENT = "1"
 *   npx playwright test engagement/
 *
 * ## Playwright traps respected here (all recorded in CLAUDE.md)
 *
 * - `getByRole` name matching is SUBSTRING — `exact: true` wherever a sibling
 *   widget could also match.
 * - `check()`/`uncheck()` fail on auto-save checkboxes; the intake wizard
 *   auto-saves, so service selection uses `click()`.
 * - Post-Run-AI state is read after `page.reload()` (StrictMode double-load).
 * - `textContent`, never `innerText`, when reading wording (`innerText` returns
 *   CSS-TRANSFORMED text, so an uppercased heading reads back uppercased).
 * - Positive state first: every screen waits on something that must APPEAR
 *   before anything is read off it, because a `toHaveCount(0)` on a page still
 *   mid-fetch passes vacuously.
 */

// ---------------------------------------------------------------------------
// Opt-in gate. Must be module-level so no test in the file executes.
// ---------------------------------------------------------------------------

test.skip(
  process.env.SHIELD_FULL_ENGAGEMENT !== "1",
  "Full-engagement demo run — opt-in observation instrument; set SHIELD_FULL_ENGAGEMENT=1 (see the file header). Excluded from CI's bare `npx playwright test`.",
);

test.use({ video: "on", trace: "on" });

// One continuous walk of the whole product. Generous, and deliberately not
// `test.slow()` (which only triples the 90s project timeout).
const RUN_BUDGET_MS = 45 * 60_000;

// ---------------------------------------------------------------------------
// Output folder. `e2e/artifacts/` is already gitignored (.gitignore:58,
// confirmed with `git check-ignore -v` rather than by reading the file), so the
// dated subfolder underneath it needs no new entry and no negation.
// ---------------------------------------------------------------------------

const RUN_STAMP = new Date()
  .toISOString()
  .replace(/[:.]/g, "-")
  .replace("T", "_")
  .slice(0, 19);
const RUN_DIR = path.resolve(
  __dirname,
  "..",
  "artifacts",
  `engagement-${RUN_STAMP}`,
);

// ---------------------------------------------------------------------------
// Step log
// ---------------------------------------------------------------------------

/**
 * Three outcomes, not two.
 *
 * `unreachable` is separated from `failed` on purpose: CLAUDE.md's fail-closed
 * rule is that "I could not look" must never share a branch with "nothing to
 * complain about", and the same distinction is what makes this log readable.
 * "The Release button never appeared" and "the release request returned 500"
 * are different findings, and collapsing them costs the reader the diagnosis.
 */
type Outcome = "ok" | "failed" | "unreachable";

/** Which surface actually performed the step. */
type Via = "ui" | "api" | "api-fallback" | "n/a";

interface StepRecord {
  seq: number;
  phase: string;
  name: string;
  outcome: Outcome;
  via: Via;
  ms: number;
  detail: string;
}

/** Thrown when an affordance never rendered — an observation, not a crash. */
class Unreachable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "Unreachable";
  }
}

class Recorder {
  readonly steps: StepRecord[] = [];
  readonly notes: string[] = [];
  private seq = 0;

  /** A free-text observation that is not itself a step. */
  note(text: string): void {
    this.notes.push(text);
    // eslint-disable-next-line no-console
    console.log(`      note  ${text}`);
  }

  /**
   * Run one step and record what happened.
   *
   * The record is written AFTER the body resolves, never before — CLAUDE.md:
   * "a success record must be written where the success is". A record written
   * above the work claims an outcome the run may not have reached.
   *
   * Returns the body's value on success and `undefined` on failure, so a caller
   * can carry on with a missing id rather than unwinding the whole run.
   */
  async step<T>(
    phase: string,
    name: string,
    via: Via,
    body: () => Promise<T>,
  ): Promise<T | undefined> {
    const started = Date.now();
    this.seq += 1;
    const seq = this.seq;
    try {
      const value = await body();
      const ms = Date.now() - started;
      this.steps.push({ seq, phase, name, outcome: "ok", via, ms, detail: "" });
      // eslint-disable-next-line no-console
      console.log(`  ok    [${phase}] ${name} (${via}, ${ms}ms)`);
      return value;
    } catch (err) {
      const ms = Date.now() - started;
      const unreachable = err instanceof Unreachable;
      const detail = describe(err);
      this.steps.push({
        seq,
        phase,
        name,
        outcome: unreachable ? "unreachable" : "failed",
        via,
        ms,
        detail,
      });
      // eslint-disable-next-line no-console
      console.log(
        `  ${unreachable ? "MISS " : "FAIL "} [${phase}] ${name} (${via}, ${ms}ms) — ${detail}`,
      );
      return undefined;
    }
  }
}

function describe(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  return raw.replace(/\s+/g, " ").slice(0, 400);
}

/**
 * Wait for an affordance and hand it back, or report it UNREACHABLE.
 *
 * The distinction this preserves is the reason the whole run does not stop: a
 * button that never rendered is a finding about that one screen, and the four
 * services after it are still worth walking.
 */
async function affordance(
  loc: Locator,
  label: string,
  timeout = 30_000,
): Promise<Locator> {
  try {
    await loc.waitFor({ state: "visible", timeout });
  } catch {
    throw new Unreachable(`affordance never appeared: ${label}`);
  }
  return loc;
}

// ---------------------------------------------------------------------------
// Engagement shape
// ---------------------------------------------------------------------------

/**
 * The four workspace services, plus the client-level Risk Register handled
 * separately. Zero Trust is represented by CISA ZTMM 2.0, matching the seed and
 * the rest of the suite; the DoD ZTRA variant is a fifth workspace this run does
 * NOT open, stated here so its absence reads as a choice rather than an
 * oversight.
 */
interface ServiceSpec {
  /** `service_type` as the intake wizard and the API both spell it. */
  type: string;
  /** Label on the intake service checkbox (`SERVICE_LABELS`). */
  intakeLabel: string;
  /** Short token used in artifact filenames and the log. */
  slug: string;
  /** `/admin/services/{id}/<segment>` */
  workspaceSegment: string;
  /** API prefix for this service's routes. */
  apiPrefix: string;
  /** `/dashboards/<segment>/{serviceId}` */
  dashboardSegment: string;
}

const SERVICES: ServiceSpec[] = [
  {
    type: "nist_csf",
    intakeLabel: "NIST CSF 2.0 Assessment",
    slug: "NIST-CSF",
    workspaceSegment: "csf",
    apiPrefix: "csf",
    dashboardSegment: "csf",
  },
  {
    type: "zero_trust_cisa",
    intakeLabel: "Zero Trust Assessment (CISA ZTMM 2.0)",
    slug: "Zero-Trust-CISA",
    workspaceSegment: "zero-trust-cisa",
    apiPrefix: "zt",
    dashboardSegment: "zt",
  },
  {
    type: "attack_coverage",
    intakeLabel: "MITRE ATT&CK Coverage Mapping",
    slug: "MITRE-ATTACK",
    workspaceSegment: "attack-coverage",
    apiPrefix: "attack",
    dashboardSegment: "attack",
  },
  {
    type: "tech_debt",
    intakeLabel: "Technical Debt Review",
    slug: "Tech-Debt",
    workspaceSegment: "tech-debt",
    apiPrefix: "tech-debt",
    dashboardSegment: "tech-debt",
  },
];

/**
 * The inventory Tech Debt extracts from. Same four rows `s4-techdebt` uses, so
 * the fixture extractor stamps the same deterministic confidences (60/70/80/90)
 * and a run is comparable to that spec's.
 */
const INVENTORY_CSV =
  "name,vendor,category,annual_cost_usd,license_count\n" +
  "CrowdStrike Falcon,CrowdStrike,EDR,120000,500\n" +
  "Splunk Enterprise,Splunk,SIEM,200000,100\n" +
  "Okta,Okta,IAM,60000,500\n" +
  "Tenable Nessus,Tenable,VulnScan,40000,50\n";

// ---------------------------------------------------------------------------
// Small helpers over the Next proxy. `page.request` shares the browser
// context's cookies, so these run as whoever is currently signed in — the same
// authorisation the screen next to them is using, which is the point.
// ---------------------------------------------------------------------------

async function proxyJson<T>(
  page: Page,
  method: "get" | "post" | "patch",
  url: string,
  data?: unknown,
): Promise<T> {
  const res = await page.request[method](
    url,
    data === undefined ? undefined : { data },
  );
  if (!res.ok()) {
    throw new Error(
      `${method.toUpperCase()} ${url} -> ${res.status()} ${(await res.text()).slice(0, 200)}`,
    );
  }
  return (await res.json()) as T;
}

/** Point the admin's client switcher at `clientId` via the cookie route. */
async function setActiveClient(page: Page, clientId: string): Promise<void> {
  const res = await page.request.post("/api/active-client", {
    data: { clientId },
  });
  if (!res.ok()) throw new Error(`set active client -> ${res.status()}`);
}

/**
 * Save one artifact to the run folder, named by SERVICE and CLIENT.
 *
 * ## Why `page.request.get` and not the download event
 *
 * The app writes artifacts server-side and serves them through
 * `/api/proxy/artifacts/{id}/download`, and every existing spec that asserts an
 * export (`s8-risk-register`, `demo/demo-journey`) fetches that route and writes
 * the bytes with `fs`. Two reasons to follow it rather than
 * `page.waitForEvent("download")`:
 *
 *  - The route responds with `Content-Disposition`, so a link click in Chromium
 *    is a download in some paths and a navigation in others. Fetching the route
 *    is deterministic; waiting on a download event is a race with the renderer.
 *  - `page.request` carries the browser context's session cookie, so the bytes
 *    are fetched under exactly the identity whose screen is on camera. A
 *    download triggered from a link proves the same thing and gives you no
 *    handle on the bytes when it does not fire.
 *
 * The UI link is still exercised: `walkDeliverableLinks` waits on it being
 * visible before the fetch, so "the link renders" and "the bytes are real" are
 * two separate observations rather than one conflated one.
 */
async function saveArtifact(
  page: Page,
  rec: Recorder,
  opts: {
    artifactId: string | null;
    filename: string | null;
    serviceSlug: string;
    clientSlug: string;
    kind: string;
  },
): Promise<void> {
  const { artifactId, filename, serviceSlug, clientSlug, kind } = opts;
  await rec.step(
    "artifacts",
    `download ${serviceSlug} ${kind}`,
    "api",
    async () => {
      if (!artifactId) {
        throw new Unreachable(
          `no ${kind} artifact id on the ${serviceSlug} deliverable`,
        );
      }
      const res = await page.request.get(
        `/api/proxy/artifacts/${artifactId}/download`,
      );
      if (res.status() !== 200) {
        throw new Error(`download -> ${res.status()}`);
      }
      const body = await res.body();
      const served = filename ?? `${serviceSlug}.${kind}`;
      const out = path.join(
        RUN_DIR,
        `${clientSlug}__${serviceSlug}__${served}`,
      );
      fs.writeFileSync(out, body);
      rec.note(
        `saved ${path.basename(out)} (${body.length} bytes, served as ${served})`,
      );
    },
  );
}

interface DeliverableShape {
  id?: string;
  version?: number;
  released_at?: string | null;
  pdf_artifact_id?: string | null;
  pdf_filename?: string | null;
  xlsx_artifact_id?: string | null;
  xlsx_filename?: string | null;
  docx_artifact_id?: string | null;
  docx_filename?: string | null;
}

/** Save whatever of PDF / XLSX / DOCX a deliverable payload carries. */
async function saveDeliverableArtifacts(
  page: Page,
  rec: Recorder,
  d: DeliverableShape,
  serviceSlug: string,
  clientSlug: string,
): Promise<void> {
  for (const kind of ["pdf", "xlsx", "docx"] as const) {
    const artifactId = d[`${kind}_artifact_id`] ?? null;
    // A service that legitimately produces no XLSX should not be logged as a
    // miss on every run, so absence is only recorded when the id is present-
    // but-unfetchable. An entirely absent id is noted instead.
    if (!artifactId) {
      rec.note(`${serviceSlug}: no ${kind} artifact on this deliverable`);
      continue;
    }
    await saveArtifact(page, rec, {
      artifactId,
      filename: d[`${kind}_filename`] ?? null,
      serviceSlug,
      clientSlug,
      kind,
    });
  }
}

/** Open a page and wait for a heading to render, as synchronisation only. */
async function visit(
  page: Page,
  rec: Recorder,
  phase: string,
  url: string,
  waitFor?: Locator,
): Promise<void> {
  await rec.step(phase, `visit ${url}`, "ui", async () => {
    await page.goto(url);
    if (waitFor) {
      await affordance(waitFor, `landmark on ${url}`, 60_000);
    } else {
      // No known landmark: settle on the network instead, so the video and the
      // trace snapshot a loaded page rather than a spinner. Never a content
      // check — just "the page stopped fetching".
      await page.waitForLoadState("networkidle").catch(() => undefined);
    }
    // Record the document title as an observation. `textContent`, not
    // `innerText`: a CSS-uppercased heading reads back uppercased and would pin
    // the styling instead of the copy.
    const h1 = page.locator("h1").first();
    const title = await h1.textContent({ timeout: 5_000 }).catch(() => null);
    rec.note(
      `${url} -> h1 ${title === null ? "(none)" : JSON.stringify(title)}`,
    );
  });
}

// ---------------------------------------------------------------------------
// The run
// ---------------------------------------------------------------------------

test("full engagement: intake -> five services -> release -> client view -> back to admin", async ({
  page,
}) => {
  test.setTimeout(RUN_BUDGET_MS);

  const rec = new Recorder();
  fs.mkdirSync(RUN_DIR, { recursive: true });

  const stamp = `${Date.now()}`;
  // A brand-new company domain provisions its own org (D-034 self-registration),
  // so this run never touches the seeded Atlas tenant. `helpers/auth.uniqueEmail`
  // defaults to `atlas.example`, which would join the EXISTING tenant — hence
  // the explicit fresh domain here rather than the helper.
  const clientDomain = `engagement-${stamp}.example`;
  const clientEmail = `demo+${stamp}@${clientDomain}`;
  const clientPassword = "DemoPass!2026";
  const legalName = `Engagement Demo ${stamp}`;
  const clientSlug = `Engagement-Demo-${stamp}`;

  rec.note(`run folder: ${RUN_DIR}`);
  rec.note(`client: ${legalName} <${clientEmail}>`);

  // Resolved as the run proceeds; a missing one degrades later steps to
  // `unreachable` rather than throwing the run away.
  const serviceIds = new Map<string, string>();
  let clientId: string | null = null;

  try {
    // === Phase 1: the client registers and completes intake ================

    await rec.step("intake", "self-register a new tenant", "ui", async () => {
      await register(page, `Demo Client ${stamp}`, clientEmail, clientPassword);
      await page.waitForURL((u) => u.pathname.startsWith("/intake"), {
        timeout: 60_000,
      });
    });

    await rec.step("intake", "select the four services", "ui", async () => {
      await affordance(
        page.getByRole("heading", { name: "Services" }).first(),
        "intake step 1 heading",
        60_000,
      );
      for (const svc of SERVICES) {
        // click(), never check(): the wizard auto-saves on change, and
        // check()/uncheck() are recorded in CLAUDE.md as failing on exactly
        // that shape.
        const box = page.getByRole("checkbox", { name: svc.intakeLabel });
        await affordance(box, `intake checkbox ${svc.intakeLabel}`);
        if (!(await box.isChecked())) await box.click();
      }
    });

    await rec.step("intake", "fill the organization step", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      const name = page.locator("#legal_name");
      await affordance(name, "legal name field");
      await name.fill(legalName);
      await page.locator("#website").fill("https://engagement-demo.example");
      await page.locator("#city").fill("Arlington");
      await page.locator("#state").fill("VA");
    });

    await rec.step("intake", "fill the contact step", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      const full = page.locator("#display_name");
      await affordance(full, "contact full-name field");
      await full.fill(`Demo Client ${stamp}`);
      await page.locator("#title").fill("CISO");
    });

    await rec.step("intake", "fill the systems step", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      await page.waitForLoadState("networkidle").catch(() => undefined);
      const systems = page.locator("textarea").first();
      if (await systems.isVisible().catch(() => false)) {
        await systems.fill(
          "Cloud-first estate: Okta IAM, CrowdStrike EDR, Splunk SIEM, Tenable VM. Two datacenters, one AWS region.",
        );
      } else {
        rec.note("systems step: no textarea found; left blank");
      }
    });

    await rec.step(
      "intake",
      "set the per-service assessment targets",
      "ui",
      async () => {
        await page.getByRole("button", { name: "Next →" }).click();
        await page.waitForLoadState("networkidle").catch(() => undefined);
        // Ids are stable and generated from the service_type
        // (`svc-${type}-tier` / `-profile` / `-stage`). Selecting by INDEX
        // rather than by option label deliberately: the label sets
        // (CSF_TARGET_TIERS, CSF_PROFILES, ZT_TARGET_STAGES) are product copy
        // this run has no business pinning.
        for (const id of [
          "#svc-nist_csf-tier",
          "#svc-nist_csf-profile",
          "#svc-zero_trust_cisa-stage",
        ]) {
          const sel = page.locator(id);
          if (await sel.isVisible().catch(() => false)) {
            await sel.selectOption({ index: 1 });
          } else {
            rec.note(`target select ${id} not present on the notes step`);
          }
        }
      },
    );

    await rec.step("intake", "submit the intake", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      const submit = page.getByRole("button", {
        name: /^(Submit|Re-submit) intake$/,
      });
      await affordance(submit, "Submit intake button", 60_000);
      // If it is disabled the wizard is telling us a target or the legal name
      // did not stick — report that rather than clicking into a no-op.
      if (await submit.isDisabled()) {
        throw new Unreachable(
          "Submit intake is disabled — a required target or the legal name did not save",
        );
      }
      await submit.click();
      await page.waitForLoadState("networkidle").catch(() => undefined);
    });

    await rec.step("intake", "client signs out", "ui", () => signOut(page));

    // === Phase 2: the admin publishes the requests into workspaces =========

    await rec.step("admin", "admin signs in", "ui", () =>
      signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD),
    );

    clientId =
      (await rec.step("admin", "resolve the new tenant", "api", async () => {
        const { clients } = await proxyJson<{
          clients: Array<{ id: string; legal_name: string }>;
        }>(page, "get", "/api/proxy/admin/clients");
        const mine = clients.find((c) => c.legal_name === legalName);
        if (!mine) throw new Error(`tenant ${legalName} not in the admin list`);
        await setActiveClient(page, mine.id);
        return mine.id;
      })) ?? null;

    if (clientId) {
      await visit(
        page,
        rec,
        "admin",
        `/admin/queue/${clientId}`,
        page.getByRole("heading").first(),
      );

      await rec.step(
        "admin",
        "publish every requested service for processing",
        "ui",
        async () => {
          // One "Publish for processing" button per unfulfilled request. Each
          // click re-renders the list, so re-query rather than holding handles.
          for (let i = 0; i < SERVICES.length + 2; i += 1) {
            const btn = page
              .getByRole("button", { name: "Publish for processing" })
              .first();
            if (!(await btn.isVisible().catch(() => false))) break;
            await btn.click();
            await page.waitForLoadState("networkidle").catch(() => undefined);
          }
          const left = await page
            .getByRole("button", { name: "Publish for processing" })
            .count();
          rec.note(`unpublished service requests remaining: ${left}`);
        },
      );

      await rec.step(
        "admin",
        "resolve the opened service ids",
        "api",
        async () => {
          const engagements = await proxyJson<
            Array<{ service_id: string; service_type: string }>
          >(page, "get", "/api/proxy/intake/assessments");
          for (const e of engagements)
            serviceIds.set(e.service_type, e.service_id);
          rec.note(
            `services opened: ${[...serviceIds.keys()].sort().join(", ") || "(none)"}`,
          );
          const missing = SERVICES.filter((s) => !serviceIds.has(s.type));
          if (missing.length) {
            // Not a throw: the run walks whatever DID open. Naming the gap here
            // is the finding.
            rec.note(
              `NOT opened by publish: ${missing.map((m) => m.type).join(", ")}`,
            );
          }
        },
      );
    }

    // === Phase 3: work each service to a released deliverable ==============

    for (const svc of SERVICES) {
      const serviceId = serviceIds.get(svc.type);
      if (!serviceId) {
        await rec.step(svc.slug, "open workspace", "ui", async () => {
          throw new Unreachable(
            `no ${svc.type} service was opened for this tenant`,
          );
        });
        continue;
      }

      await visit(
        page,
        rec,
        svc.slug,
        `/admin/services/${serviceId}/${svc.workspaceSegment}`,
        page.getByRole("heading").first(),
      );

      // --- score the assessment ------------------------------------------
      if (svc.type === "tech_debt") {
        await rec.step(
          svc.slug,
          "upload the inventory and extract",
          "ui",
          async () => {
            const extractDone = page.waitForResponse(
              (r) =>
                r.url().includes("/capability-lists/extract") &&
                r.request().method() === "POST",
              { timeout: 180_000 },
            );
            const file = page.locator('input[type="file"]').first();
            await affordance(file, "tech-debt inventory file input", 60_000);
            await file.setInputFiles({
              name: "inventory.csv",
              mimeType: "text/csv",
              buffer: Buffer.from(INVENTORY_CSV),
            });
            // Offline: the upload only LISTS the file; extraction is an
            // explicit guarded click (the Run-AI guard exists so an upload
            // cannot silently produce canned output).
            const extract = page
              .getByRole("button", { name: "Extract from this" })
              .first();
            if (await extract.isVisible().catch(() => false)) {
              await extract.click();
              await acknowledgeOfflineAi(page);
            }
            await extractDone;
          },
        );

        await rec.step(
          svc.slug,
          "approve the capability list",
          "api",
          async () => {
            const latest = await proxyJson<{ id: string; status: string }>(
              page,
              "get",
              `/api/proxy/tech-debt/services/${serviceId}/capability-lists/latest`,
            );
            rec.note(`tech-debt capability list is ${latest.status}`);
            if (latest.status === "draft") {
              await proxyJson(
                page,
                "post",
                `/api/proxy/tech-debt/capability-lists/${latest.id}/approve`,
              );
            }
          },
        );
      } else {
        await rec.step(svc.slug, "open a draft assessment", "api", async () => {
          await proxyJson(
            page,
            "post",
            `/api/proxy/${svc.apiPrefix}/services/${serviceId}/assessments`,
          );
        });

        await rec.step(
          svc.slug,
          "score the assessment rows",
          "api",
          async () => {
            // Scored through the API rather than by typing ~106 CSF cells into
            // the grid on camera. This is SETUP, not the subject: the subject
            // is what the workspace, the deliverable and the client dashboard
            // then say about it. Recorded as `api` so the log never implies a
            // human drove it.
            const latest = await proxyJson<{
              answers?: Array<{ id: string }>;
              coverage?: Array<{ id: string }>;
            }>(
              page,
              "get",
              `/api/proxy/${svc.apiPrefix}/services/${serviceId}/assessments/latest`,
            );

            if (svc.apiPrefix === "attack") {
              const rows = latest.coverage ?? [];
              // A deterministic spread so the coverage ratio is not degenerate:
              // covered / partial / gap in rotation.
              const statuses = ["covered", "partial", "gap"];
              let n = 0;
              for (const row of rows) {
                await proxyJson(
                  page,
                  "patch",
                  `/api/proxy/attack/coverage/${row.id}`,
                  { status: statuses[n % statuses.length] },
                );
                n += 1;
              }
              rec.note(`ATT&CK: scored ${n} coverage rows`);
              return;
            }

            const rows = latest.answers ?? [];
            let n = 0;
            for (const row of rows) {
              const body =
                svc.apiPrefix === "csf"
                  ? { maturity_tier: [2, 3, 2, 4][n % 4] }
                  : { maturity_stage: [1, 2, 3, 2][n % 4], target_stage: 4 };
              await proxyJson(
                page,
                "patch",
                `/api/proxy/${svc.apiPrefix}/answers/${row.id}`,
                body,
              );
              n += 1;
            }
            rec.note(`${svc.slug}: scored ${n} answer rows`);
          },
        );

        // --- Run AI, in the browser, on camera ---------------------------
        await rec.step(svc.slug, "Run AI", "ui", async () => {
          await page.reload();
          // CSF's control is labelled "Run AI (csf_score)"; ATT&CK and ZT use a
          // bare "Run AI". Matched by regex rather than by a per-service
          // literal so a copy change degrades to `unreachable` instead of a
          // silent miss.
          const runAi = page.getByRole("button", { name: /^Run AI\b/ }).first();
          await affordance(runAi, `${svc.slug} Run AI button`, 60_000);
          if (await runAi.isDisabled()) {
            throw new Unreachable(
              `${svc.slug}: Run AI is disabled at this assessment status`,
            );
          }
          const ran = page.waitForResponse(
            (r) =>
              r.url().includes("/run-ai") && r.request().method() === "POST",
            { timeout: 240_000 },
          );
          await runAi.click();
          await acknowledgeOfflineAi(page);
          const res = await ran;
          rec.note(`${svc.slug}: run-ai -> ${res.status()}`);
          // Post-Run-AI state is read after a reload: StrictMode double-loads
          // and the panel can otherwise be read mid-swap.
          await page.reload();
          await page.waitForLoadState("networkidle").catch(() => undefined);
        });

        await rec.step(svc.slug, "approve the assessment", "ui", async () => {
          // The label is status-dependent: "Approve" on a DRAFT and "Approve
          // client inputs" on a SUBMITTED one (CsfWorkspace / ZtWorkspace /
          // AttackWorkspace all share the branch). This run creates drafts, so
          // "Approve" is the expected label — but an anchored regex covering
          // both costs nothing and keeps the step from reading `unreachable`
          // if the client self-assessment path ever submits first.
          //
          // Anchored deliberately: `getByRole` name matching is SUBSTRING, so a
          // bare "Approve" would also match the DISABLED "Approved" and
          // "Approving…" states and the step would click a no-op and call it
          // done.
          const approve = page
            .getByRole("button", { name: /^Approve( client inputs)?$/ })
            .first();
          if (await approve.isVisible().catch(() => false)) {
            if (await approve.isDisabled()) {
              throw new Unreachable(`${svc.slug}: Approve is disabled`);
            }
            await approve.click();
            await page.waitForLoadState("networkidle").catch(() => undefined);
            return;
          }
          throw new Unreachable(`${svc.slug}: no Approve control on the page`);
        });

        // The UI Approve is the interesting path; if it did not land, the
        // deliverable steps below are all unreachable, which is a poor trade
        // for an instrument. Fall back through the API and SAY SO.
        await rec.step(
          svc.slug,
          "ensure the assessment is approved",
          "api-fallback",
          async () => {
            const latest = await proxyJson<{ id: string; status: string }>(
              page,
              "get",
              `/api/proxy/${svc.apiPrefix}/services/${serviceId}/assessments/latest`,
            );
            rec.note(`${svc.slug}: assessment status is ${latest.status}`);
            if (latest.status === "draft" || latest.status === "submitted") {
              await proxyJson(
                page,
                "post",
                `/api/proxy/${svc.apiPrefix}/assessments/${latest.id}/approve`,
              );
              rec.note(
                `${svc.slug}: approved via API — the UI control did not do it`,
              );
            }
          },
        );
      }

      // --- finalize and release, in the browser --------------------------
      await rec.step(svc.slug, "finalize the deliverable", "ui", async () => {
        await page.reload();
        const finalize = page
          .getByRole("button", { name: /^(Finalize|Re-finalize)$/ })
          .first();
        await affordance(finalize, `${svc.slug} Finalize button`, 60_000);
        if (await finalize.isDisabled()) {
          throw new Unreachable(
            `${svc.slug}: Finalize is disabled — the assessment is not approved`,
          );
        }
        const done = page.waitForResponse(
          (r) =>
            r.url().includes("/deliverables/finalize") &&
            r.request().method() === "POST",
          { timeout: 240_000 },
        );
        await finalize.click();
        const res = await done;
        rec.note(`${svc.slug}: finalize -> ${res.status()}`);
      });

      await rec.step(svc.slug, "release to the client", "ui", async () => {
        const release = page.getByRole("button", { name: "Release to client" });
        await affordance(release, `${svc.slug} Release control`, 60_000);
        await release.click();
        const confirm = page.getByRole("button", { name: "Yes, release" });
        await affordance(confirm, `${svc.slug} release confirm`);
        const done = page.waitForResponse(
          (r) =>
            r.url().includes("/release") && r.request().method() === "POST",
          { timeout: 120_000 },
        );
        await confirm.click();
        const res = await done;
        rec.note(`${svc.slug}: release -> ${res.status()}`);
      });

      // --- pull the generated artifacts down -----------------------------
      await rec.step(
        svc.slug,
        "read the released deliverable",
        "api",
        async () => {
          const d = await proxyJson<DeliverableShape>(
            page,
            "get",
            `/api/proxy/${svc.apiPrefix}/services/${serviceId}/deliverables/latest`,
          );
          rec.note(
            `${svc.slug}: deliverable v${d.version ?? "?"} released_at=${d.released_at ?? "null"}`,
          );
          await saveDeliverableArtifacts(page, rec, d, svc.slug, clientSlug);
        },
      );
    }

    // === Phase 4: the Risk Register (client-level, synthesized) ============

    if (clientId) {
      await visit(
        page,
        rec,
        "Risk-Register",
        "/admin/risk-register",
        page.getByRole("heading", { name: "Risk Register", exact: true }),
      );

      await rec.step("Risk-Register", "read the gate", "api", async () => {
        const g = await proxyJson<{ unlocked: boolean; missing: string[] }>(
          page,
          "get",
          `/api/proxy/risk/clients/${clientId}/gate`,
        );
        rec.note(
          `risk gate unlocked=${g.unlocked} missing=[${(g.missing ?? []).join("; ")}]`,
        );
      });

      await rec.step(
        "Risk-Register",
        "generate the register",
        "ui",
        async () => {
          const gen = page.getByRole("button", {
            name: /^(Generate|Regenerate)$/,
          });
          await affordance(gen, "Risk Register generate control", 60_000);
          const done = page.waitForResponse(
            (r) =>
              r.url().includes("/register/generate") &&
              r.request().method() === "POST",
            { timeout: 300_000 },
          );
          await gen.click();
          await acknowledgeOfflineAi(page);
          const res = await done;
          rec.note(`risk register generate -> ${res.status()}`);
        },
      );

      await rec.step(
        "Risk-Register",
        "export XLSX / PDF / Word",
        "ui",
        async () => {
          const exportBtn = page.getByRole("button", {
            name: "Export XLSX / PDF / Word",
          });
          await affordance(exportBtn, "Risk Register export control", 60_000);
          const done = page.waitForResponse(
            (r) =>
              r.url().includes("/register/export") &&
              r.request().method() === "POST",
            { timeout: 300_000 },
          );
          await exportBtn.click();
          const res = await done;
          rec.note(`risk register export -> ${res.status()}`);
        },
      );

      await rec.step(
        "Risk-Register",
        "download the register exports",
        "api",
        async () => {
          const reg = await proxyJson<DeliverableShape>(
            page,
            "get",
            `/api/proxy/risk/clients/${clientId}/register/latest`,
          );
          await saveDeliverableArtifacts(
            page,
            rec,
            reg,
            "Risk-Register",
            clientSlug,
          );
        },
      );
    }

    // === Phase 5: cross into the CLIENT view, in the same browser ==========
    //
    // Same `page`, same context. The sign-out/sign-in happens on camera and in
    // the trace, so a cookie or active-tenant defect at the crossing is
    // visible. Two separate contexts would skip exactly that.

    await rec.step("client-view", "admin signs out", "ui", () => signOut(page));
    await rec.step("client-view", "the client signs in", "ui", () =>
      signIn(page, clientEmail, clientPassword),
    );

    for (const url of [
      "/home",
      "/results",
      "/documents",
      "/assessments",
      "/messages",
      "/account",
    ]) {
      await visit(page, rec, "client-view", url);
    }

    for (const svc of SERVICES) {
      const serviceId = serviceIds.get(svc.type);
      if (!serviceId) {
        rec.note(`client-view: no ${svc.type} service to open a dashboard for`);
        continue;
      }
      await visit(
        page,
        rec,
        "client-view",
        `/dashboards/${svc.dashboardSegment}/${serviceId}`,
      );
    }
    await visit(page, rec, "client-view", "/dashboards/risk");

    // The client's own download links — the second half of "the document and
    // the dashboard agree": these are fetched under the CLIENT's session, not
    // the admin's, so a tenant-scoping defect shows up as a status code here.
    await rec.step(
      "client-view",
      "client fetches its own reports",
      "api",
      async () => {
        await page.goto("/results");
        await page.waitForLoadState("networkidle").catch(() => undefined);
        const links = page.getByRole("link", {
          name: /PDF|XLSX|Word|Download/i,
        });
        const n = await links.count();
        rec.note(`client /results exposes ${n} download link(s)`);
      },
    );

    // === Phase 6: back to admin, and walk the workspace ====================

    await rec.step("admin-walk", "client signs out", "ui", () => signOut(page));
    await rec.step("admin-walk", "admin signs back in", "ui", () =>
      signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD),
    );
    if (clientId) {
      await rec.step("admin-walk", "re-align the active tenant", "api", () =>
        setActiveClient(page, clientId as string),
      );
    }

    const adminPages = [
      "/admin",
      "/admin/queue",
      "/admin/deliverables",
      "/admin/risk-register",
      "/admin/management",
      "/admin/audit",
      "/admin/health",
      "/admin/messages",
    ];
    for (const url of adminPages) {
      await visit(page, rec, "admin-walk", url);
    }
    if (clientId) {
      await visit(page, rec, "admin-walk", `/admin/queue/${clientId}`);
    }

    // And back through each workspace, now that everything is released — the
    // return crossing, which is where a released-state renderer defect lives.
    for (const svc of SERVICES) {
      const serviceId = serviceIds.get(svc.type);
      if (!serviceId) continue;
      await visit(
        page,
        rec,
        "admin-walk",
        `/admin/services/${serviceId}/${svc.workspaceSegment}`,
      );
    }
  } finally {
    // Written in `finally` so a hard failure anywhere above still leaves a
    // legible record. An instrument whose log only survives a clean run tells
    // you least exactly when you need it most.
    const video = await page.video()?.path();
    writeLog(rec, {
      legalName,
      clientEmail,
      clientId,
      serviceIds,
      videoPath: video ?? null,
      outputDir: test.info().outputDir,
    });
  }
});

// ---------------------------------------------------------------------------
// Log writer
// ---------------------------------------------------------------------------

function writeLog(
  rec: Recorder,
  ctx: {
    legalName: string;
    clientEmail: string;
    clientId: string | null;
    serviceIds: Map<string, string>;
    videoPath: string | null;
    outputDir: string;
  },
): void {
  const ok = rec.steps.filter((s) => s.outcome === "ok").length;
  const failed = rec.steps.filter((s) => s.outcome === "failed").length;
  const missed = rec.steps.filter((s) => s.outcome === "unreachable").length;

  const lines: string[] = [];
  lines.push(`# Full-engagement observation run — ${RUN_STAMP}`);
  lines.push("");
  lines.push(
    "This run asserts nothing about content. Every line below is an OBSERVATION.",
  );
  lines.push(
    "A `failed` or `unreachable` row is a finding to look at, not a broken test.",
  );
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(`- steps recorded: ${rec.steps.length}`);
  lines.push(`- ok: ${ok}`);
  lines.push(`- failed: ${failed}`);
  lines.push(`- unreachable (affordance never appeared): ${missed}`);
  lines.push("");
  lines.push("## Engagement");
  lines.push("");
  lines.push(`- client: ${ctx.legalName}`);
  lines.push(`- login: ${ctx.clientEmail} / DemoPass!2026`);
  lines.push(`- client id: ${ctx.clientId ?? "(never resolved)"}`);
  for (const [type, id] of [...ctx.serviceIds.entries()].sort()) {
    lines.push(`- service ${type}: ${id}`);
  }
  lines.push("");
  lines.push("## Video and trace");
  lines.push("");
  lines.push(
    `Playwright writes both under its own output dir, NOT into this folder:`,
  );
  lines.push("");
  lines.push(`    ${ctx.outputDir}`);
  lines.push("");
  lines.push(`- video: ${ctx.videoPath ?? "(path not available)"}`);
  lines.push(
    "- trace: `trace.zip` in that folder — open with `npx playwright show-trace <path>`",
  );
  lines.push("");
  lines.push(
    "The video file is finalized when the browser context closes, which happens",
  );
  lines.push(
    "AFTER this log is written — so the path above is correct while the file may",
  );
  lines.push("appear a moment later.");
  lines.push("");
  lines.push("## Steps");
  lines.push("");
  lines.push("| # | phase | step | outcome | via | ms | detail |");
  lines.push("| --- | --- | --- | --- | --- | --- | --- |");
  for (const s of rec.steps) {
    const detail = s.detail.replace(/\|/g, "\\|");
    lines.push(
      `| ${s.seq} | ${s.phase} | ${s.name} | ${s.outcome} | ${s.via} | ${s.ms} | ${detail} |`,
    );
  }
  lines.push("");
  lines.push("## Notes");
  lines.push("");
  for (const n of rec.notes) lines.push(`- ${n.replace(/\|/g, "\\|")}`);
  lines.push("");

  fs.mkdirSync(RUN_DIR, { recursive: true });
  fs.writeFileSync(path.join(RUN_DIR, "step-log.md"), lines.join("\n"), "utf8");
  fs.writeFileSync(
    path.join(RUN_DIR, "step-log.json"),
    JSON.stringify(
      {
        stamp: RUN_STAMP,
        summary: { total: rec.steps.length, ok, failed, unreachable: missed },
        engagement: {
          legalName: ctx.legalName,
          clientEmail: ctx.clientEmail,
          clientId: ctx.clientId,
          services: Object.fromEntries(ctx.serviceIds),
        },
        videoPath: ctx.videoPath,
        outputDir: ctx.outputDir,
        steps: rec.steps,
        notes: rec.notes,
      },
      null,
      2,
    ),
    "utf8",
  );

  // eslint-disable-next-line no-console
  console.log(
    `\nfull-engagement: ${ok} ok, ${failed} failed, ${missed} unreachable — ${RUN_DIR}\n`,
  );
}
