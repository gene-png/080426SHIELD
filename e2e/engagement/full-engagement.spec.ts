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
 * the `affordance()` helper, which converts a TIMEOUT into a recorded
 * `unreachable` observation instead of a failure — so a screen that never
 * rendered is logged and the run CONTINUES to the next service.
 *
 * Of the two helpers this file calls, only `helpers/auth` asserts internally;
 * `helpers/ai` contains no assertion at all and returns silently when the
 * offline dialog is absent. Either way a throw from either surfaces as a
 * recorded `failed` step rather than an aborted run, because both are only ever
 * called inside a `rec.step` body.
 *
 * ## The rule this file kept breaking, stated once
 *
 * **Every place this spec writes an outcome, "I could not look" must be a
 * DIFFERENT recorded value from "I looked and it was not there" and from "I
 * looked and it was fine."** See the `Outcome` type for the four kinds.
 *
 * That is not a style preference. A step that reads state off a page which
 * never finished loading and records `ok` does not lose information, it
 * MANUFACTURES a finding — and a manufactured finding in a log whose whole
 * purpose is to be believed is worse than no log. The first draft of this file
 * did exactly that throughout: `isVisible()` and `count()` return immediately,
 * and sat behind `waitForLoadState("networkidle").catch(() => undefined)`,
 * which swallows its own timeout. The worst instance read an error card as a
 * loaded intake queue and wrote "publishing silently fails to open workspaces"
 * about a product that does nothing of the kind.
 *
 * The sites are not enumerated here, because an enumeration goes stale the next
 * time one is added or fixed. The shape is greppable instead, and a hit is a
 * defect unless it is waiting first:
 *
 *     grep -nE "isVisible\(\)|\.count\(\)|isDisabled\(\)|networkidle\"\)\.catch" \
 *       e2e/engagement/full-engagement.spec.ts
 *
 * So, when editing this file: anything that decides a step's outcome waits
 * first — `affordance()` or `settled()`, never a bare `isVisible()`/`count()` —
 * and where it cannot, it records `Indeterminate` rather than `ok` and rather
 * than a specific cause invented to explain a symptom. `visit()` does not treat
 * "some heading exists" as arrival, because the house error card is a heading.
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
 * **AFTERWARDS: `seed_demo.py` becomes a silent no-op, and this run is the
 * reason.** The seed's guard is "does ANY `Service` row exist, for ANY tenant".
 * This spec mints a tenant and four `Service` rows, so a later
 * `docker compose exec -T api python scripts/seed_demo.py` prints "Services
 * already present; skipping seeding." and exits **0** — a success message over
 * a seed that did nothing. The only recovery is `docker compose down -v`.
 *
 * That is not this spec's defect (it is #65, and every spec minting a service
 * does it), but this one is the most likely to be run just before a demo, which
 * is exactly when someone re-seeds for a clean stack and is told it worked. The
 * list above is not exhaustive; this is the item most likely to bite next.
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
// Output folder. The dated subfolder needs no new ignore entry and no
// negation: `.gitignore` already carries the entry `e2e/artifacts/`, which
// covers everything beneath it.
//
// Confirmed by RUNNING `git check-ignore -v e2e/artifacts/engagement-x/f.pdf`
// rather than by reading the file — and cited by the quoted entry rather than
// by a line number, because a line number is a property of a tree and not of a
// document. An earlier version of this comment said ".gitignore:58"; the fact
// was verified correctly and the citation was still written the one way
// CLAUDE.md rules out.
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
 * FOUR outcomes, and the fourth is the one this instrument kept getting wrong.
 *
 * CLAUDE.md's fail-closed rule is that "I could not look" must never share a
 * branch with "nothing to complain about". These four keep three different
 * questions apart, and every one of them was collapsed into another at least
 * once in the first draft of this file:
 *
 *  - `ok`            — I looked, and it was fine.
 *  - `failed`        — I looked, and it went wrong. Carries the real error.
 *  - `unreachable`   — I looked, and the thing was not there within budget.
 *  - `indeterminate` — I COULD NOT LOOK. The page never settled, the locator
 *                      was ambiguous, the read raced the render. No claim is
 *                      made about the product at all.
 *
 * The distinction is not pedantry, it is the difference between a true log and
 * a false one. A step that reads state off a page which never finished loading
 * and records `ok` does not merely lose information — it MANUFACTURES a
 * finding. `unpublished service requests remaining: 0` read off an error card
 * is a sentence about a defect that does not exist, and it is indistinguishable
 * from the real thing at the point where someone reads it.
 *
 * So: anything that decides a step's outcome must WAIT first. Where it cannot,
 * the answer is `indeterminate` — never `ok`, and never a specific cause
 * invented to explain a symptom.
 */
type Outcome = "ok" | "failed" | "unreachable" | "indeterminate";

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

/**
 * Thrown when the run could not establish what the product was doing.
 *
 * Distinct from `Unreachable` on purpose: "the button was not there" is a claim
 * about the page, and "I could not tell whether the button was there" is a
 * claim about the run. Recording the second as the first invents a defect.
 */
class Indeterminate extends Error {
  constructor(message: string) {
    super(message);
    this.name = "Indeterminate";
  }
}

class Recorder {
  readonly steps: StepRecord[] = [];
  readonly notes: string[] = [];
  private seq = 0;

  /** Next row number. Called at PUSH time so `#` always equals row position. */
  private nextSeq(): number {
    this.seq += 1;
    return this.seq;
  }

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
    // The sequence number is assigned when the record is PUSHED, not on entry.
    //
    // Steps nest — the per-artifact downloads run inside "read the released
    // deliverable" — and a nested step finishes first, so it is pushed first.
    // Numbering on entry made the `#` column read 21, 22, 23, 20 down the page,
    // and a column headed `#` reads as order. Numbering at push keeps `#`
    // identical to the row's position, so it can never disagree with what the
    // reader sees. The ordering is COMPLETION order, which the log says.
    try {
      const value = await body();
      const ms = Date.now() - started;
      const seq = this.nextSeq();
      this.steps.push({ seq, phase, name, outcome: "ok", via, ms, detail: "" });
      // eslint-disable-next-line no-console
      console.log(`  ok    [${phase}] ${name} (${via}, ${ms}ms)`);
      return value;
    } catch (err) {
      const ms = Date.now() - started;
      const outcome: Outcome =
        err instanceof Unreachable
          ? "unreachable"
          : err instanceof Indeterminate
            ? "indeterminate"
            : "failed";
      const detail = describe(err);
      const seq = this.nextSeq();
      this.steps.push({ seq, phase, name, outcome, via, ms, detail });
      const marker = {
        unreachable: "MISS ",
        indeterminate: "?????",
        failed: "FAIL ",
      }[outcome as Exclude<Outcome, "ok">];
      // eslint-disable-next-line no-console
      console.log(
        `  ${marker} [${phase}] ${name} (${via}, ${ms}ms) — ${detail}`,
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
 * Wait for an affordance and hand it back, classifying a failure HONESTLY.
 *
 * A bare `catch` here is a bug, and it was one: `locator.waitFor` rejects for at
 * least four different reasons, and only ONE of them means "it never appeared".
 * Relabelling all four as `Unreachable` writes a confident, specific, wrong
 * sentence into the log — Gene reads "the Release button never rendered", opens
 * the video, and finds two of them.
 *
 *  - `TimeoutError`            -> genuinely not there within budget: `unreachable`.
 *  - strict-mode violation     -> the locator matched 2+ elements. That is a
 *                                REAL finding about the page, so the original
 *                                error propagates and is recorded `failed` with
 *                                Playwright's own message naming the count.
 *  - page/context/browser closed -> the run cannot look at all: `indeterminate`.
 *  - anything else             -> propagate unchanged rather than guess.
 *
 * Deliberately NOT fixed by adding `.first()` to the ambiguous call sites
 * (`Release to client`, `Yes, release`, `Export XLSX / PDF / Word`,
 * `/^(Generate|Regenerate)$/`). `.first()` would silently pick one of two
 * buttons and record `ok` — it hides exactly the defect this instrument exists
 * to surface. They stay strict, and a duplicate now reports itself accurately.
 */
async function affordance(
  loc: Locator,
  label: string,
  timeout = 30_000,
): Promise<Locator> {
  try {
    await loc.waitFor({ state: "visible", timeout });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const name = err instanceof Error ? err.name : "";
    if (/has been closed|Target crashed/i.test(message)) {
      throw new Indeterminate(
        `could not look for ${label}: ${message.split("\n")[0]}`,
      );
    }
    if (name === "TimeoutError") {
      throw new Unreachable(
        `affordance never appeared within ${timeout}ms: ${label}`,
      );
    }
    throw err;
  }
  return loc;
}

/**
 * Wait for the network to go quiet, and REPORT whether it did.
 *
 * `waitForLoadState("networkidle").catch(() => undefined)` is the shape that
 * made this instrument lie: it swallows its own timeout, so the next line reads
 * state off a page that may still be fetching and records the result as fact.
 * Callers must branch on the return value rather than ignoring it.
 */
async function settled(page: Page, timeout = 20_000): Promise<boolean> {
  try {
    await page.waitForLoadState("networkidle", { timeout });
    return true;
  } catch {
    return false;
  }
}

/**
 * The house error card: every failed fetch in this app renders a card titled
 * "Couldn't load ..." (IntakeQueue, CsfWorkspace, ZtWorkspace, AttackWorkspace,
 * TechDebtWorkspace, AssessmentsView, IntakeWizard, both self-assessments), or
 * sets an inline `[role="alert"]`. Derived as a PREDICATE over that shape rather
 * than enumerated per page, so a new error surface is caught without an edit.
 *
 * Returns the error text if the page is showing one, else null.
 *
 * THE TWO BARE `isVisible()` CALLS BELOW ARE DELIBERATE, and they are the only
 * ones in this file. Everywhere else a bare `isVisible()` is the defect
 * described in the header; here it is correct, and the difference is worth
 * stating because the grep in that header hits these two lines.
 *
 * This is a "is an error on screen RIGHT NOW" probe, not a decision about
 * whether something arrived. Waiting would invert its meaning: `waitFor` on an
 * error card would sit for the full timeout on every healthy page and then
 * report no error — the correct answer reached slowly, on every single call.
 * And a null return is never treated as proof of health; it only means "no
 * error was showing at this instant", after which the CALLER still has to
 * establish arrival positively (`settled()`, then an `<h1>` or an
 * `affordance()`). So this function can produce a false negative and nothing
 * downstream depends on it not doing so.
 */
async function errorCardText(page: Page): Promise<string | null> {
  const card = page.getByRole("heading", { name: /Couldn.t load/i }).first();
  if (await card.isVisible().catch(() => false)) {
    return (await card.textContent().catch(() => null)) ?? "Couldn't load (…)";
  }
  const alert = page.getByRole("alert").first();
  if (await alert.isVisible().catch(() => false)) {
    return (await alert.textContent().catch(() => null)) ?? "[role=alert]";
  }
  return null;
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
      // RAISE, do not note. A 200 carrying nothing is a real product defect —
      // a truncated or missing MinIO object served as a success — and it must
      // be loud rather than a byte count someone has to go and read.
      //
      // Writing it would be worse than losing it: the FOLDER is what gets
      // opened first, and a 0-byte file with a confident
      // `<Client>__<Service>__<name>.pdf` name is indistinguishable from a real
      // deliverable until it opens to nothing. Never create that file.
      if (body.length === 0) {
        throw new Error(
          `download -> 200 with an EMPTY body (${kind}, artifact ${artifactId}); nothing written`,
        );
      }
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

/**
 * Open a page and establish, honestly, whether it LOADED.
 *
 * The first draft waited on `page.getByRole("heading").first()` and called that
 * arrival. It is not arrival. `IntakeQueue` early-returns an error card on a
 * failed fetch, that card's title is a `CardTitle` — an `<h3>` — and it
 * satisfies "some heading exists" perfectly. So a queue that failed to load was
 * recorded `ok`, and three steps downstream read state off it and wrote a
 * product defect into the log that did not exist.
 *
 * The house pattern makes a real discriminator available: on success these
 * pages render an `<h1>`; the error card renders no `<h1>` at all. So:
 *
 *  - error card or inline alert visible -> `failed`, quoting what it said.
 *  - `<h1>` present                     -> `ok`, recording its text.
 *  - neither, and the network settled   -> `ok` with a note (some pages have no
 *                                          `<h1>`; that is not a fault).
 *  - neither, and it never settled      -> `indeterminate`. No claim is made.
 *
 * The HTTP status from `goto` is recorded either way — the most primitive
 * signal available, and the one that survives any renderer confusion.
 */
async function visit(
  page: Page,
  rec: Recorder,
  phase: string,
  url: string,
): Promise<void> {
  await rec.step(phase, `visit ${url}`, "ui", async () => {
    const response = await page.goto(url);
    const status = response ? response.status() : null;
    const quiet = await settled(page);

    const errorText = await errorCardText(page);
    if (errorText !== null) {
      throw new Error(
        `${url} rendered an error state (HTTP ${status ?? "?"}): ${errorText.trim().slice(0, 200)}`,
      );
    }

    // `textContent`, not `innerText`: a CSS-uppercased heading reads back
    // uppercased and would pin the styling instead of the copy.
    const h1 = page.locator("h1").first();
    const title = await h1.textContent({ timeout: 5_000 }).catch(() => null);

    if (title === null && !quiet) {
      throw new Indeterminate(
        `${url}: no <h1> and the network never went quiet (HTTP ${status ?? "?"}) — cannot say whether this page loaded`,
      );
    }
    rec.note(
      `${url} -> HTTP ${status ?? "?"}, settled=${quiet}, h1 ${
        title === null ? "(none — page has no h1)" : JSON.stringify(title)
      }`,
    );
  });
}

// ---------------------------------------------------------------------------
// Run state, hoisted so the log survives a TIMEOUT
// ---------------------------------------------------------------------------

/**
 * Everything `writeLog` needs, held at module scope and populated as the run
 * proceeds.
 *
 * ## Why this is not a local inside a `try/finally`
 *
 * It was, and the `finally`'s own comment claimed it meant "a hard failure
 * anywhere above still leaves a legible record". That was FALSE for the most
 * probable hard failure this run has.
 *
 * Playwright does not unwind a test body when the test times out — it abandons
 * the pending `await` and tears the fixtures down, so a `finally` in the body
 * never executes. `afterEach` hooks DO run after a timeout. With a 45-minute
 * budget across roughly forty steps, several of which wait up to 240s on Run-AI
 * and 300s on the register, a timeout is the single most likely way this run
 * ends badly — and it is exactly the run whose partial record is worth most.
 *
 * **MEASURED 2026-09-09, not inferred.** A throwaway spec with a 3s test
 * timeout awaited 30s inside a `try`, with a `finally` and an `afterEach` each
 * appending a marker. Complete output: `afterEach RAN`. The `finally` marker
 * never appeared and the body never completed. So the `finally` genuinely did
 * lose the log on a timeout, and `afterEach` genuinely saves it.
 *
 * **What that covers, and only that:** Playwright's lifecycle on a TEST
 * TIMEOUT, on this version, in a spec that navigated nowhere. It says nothing
 * about a crashed browser, a killed process, or a `globalTeardown` failure —
 * for those, the `logged` flag and the early video-handle capture below are
 * still reasoned rather than measured. One measurement does not certify its
 * neighbours.
 *
 * The per-step `console.log` in `Recorder.step` is kept regardless. It is the
 * mitigation that needs no hook to fire, because it writes as the run goes
 * rather than at the end — and it is what would still survive the three cases
 * above that nobody has measured.
 */
interface RunState {
  rec: Recorder;
  legalName: string;
  clientEmail: string;
  clientId: string | null;
  serviceIds: Map<string, string>;
  /** Captured early: after a timeout the page may be gone, the handle is not. */
  video: ReturnType<Page["video"]>;
  /** True only if the walk ran to the end — distinguishes a partial log. */
  completed: boolean;
  logged: boolean;
}

let runState: RunState | null = null;

test.afterEach(async () => {
  if (runState === null || runState.logged) return;
  runState.logged = true;
  let videoPath: string | null = null;
  try {
    videoPath = (await runState.video?.path()) ?? null;
  } catch {
    videoPath = null; // page torn down; the path is a convenience, not the record
  }
  writeLog(runState.rec, {
    legalName: runState.legalName,
    clientEmail: runState.clientEmail,
    clientId: runState.clientId,
    serviceIds: runState.serviceIds,
    videoPath,
    outputDir: test.info().outputDir,
    completed: runState.completed,
  });
});

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

  // Publish the state the afterEach hook logs from. `serviceIds` is shared by
  // REFERENCE, so entries added below are visible without a further assignment;
  // `clientId` is a primitive and must be copied across when it is resolved.
  // Assigned here, before the first step, so a timeout in the very first phase
  // still produces a log rather than nothing.
  runState = {
    rec,
    legalName,
    clientEmail,
    clientId: null,
    serviceIds,
    video: page.video(),
    completed: false,
    logged: false,
  };

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
        // Verify the RESULT, do not assume the click landed. A pre-hydration
        // `isChecked()` reads the DOM default, so a box that was already on
        // could be toggled OFF here — silently dropping a service from the
        // engagement, which then reads downstream as "publish never opened it".
        // Cheap to check, and the failure mode is the expensive kind.
        if (!(await box.isChecked())) await box.click();
        if (!(await box.isChecked())) {
          await box.click();
          if (!(await box.isChecked())) {
            throw new Unreachable(
              `intake: ${svc.intakeLabel} would not stay checked after two clicks`,
            );
          }
        }
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
      if (!(await settled(page))) {
        throw new Indeterminate(
          "the systems step never went quiet — cannot tell whether its field rendered",
        );
      }
      const systems = page.locator("textarea").first();
      // A real wait. `isVisible()` on a step that is still rendering answers
      // "no" and the run records "no textarea found" about a field that was
      // simply late.
      try {
        await systems.waitFor({ state: "visible", timeout: 15_000 });
      } catch {
        rec.note(
          "systems step: no textarea after a 15s wait; left blank (this is an observation, not a failure)",
        );
        return;
      }
      await systems.fill(
        "Cloud-first estate: Okta IAM, CrowdStrike EDR, Splunk SIEM, Tenable VM. Two datacenters, one AWS region.",
      );
    });

    // Threaded into the submit step below so a disabled Submit is never
    // explained by a cause this run did not establish.
    const targetsSet: string[] = [];
    const targetsMissing: string[] = [];

    await rec.step(
      "intake",
      "set the per-service assessment targets",
      "ui",
      async () => {
        await page.getByRole("button", { name: "Next →" }).click();
        if (!(await settled(page))) {
          throw new Indeterminate(
            "the notes step never went quiet — cannot tell which target selects rendered",
          );
        }
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
          try {
            await sel.waitFor({ state: "visible", timeout: 15_000 });
          } catch {
            targetsMissing.push(id);
            rec.note(`target select ${id}: not visible after a 15s wait`);
            continue;
          }
          await sel.selectOption({ index: 1 });
          targetsSet.push(id);
        }
      },
    );

    await rec.step("intake", "submit the intake", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      const submit = page.getByRole("button", {
        name: /^(Submit|Re-submit) intake$/,
      });
      await affordance(submit, "Submit intake button", 60_000);

      // Submit is disabled while `picks.length === 0 || !legalName ||
      // targetsIncomplete` (Step6Review). The first draft read a disabled
      // button and asserted ONE of those three as the cause. It had no basis
      // for choosing — that is an invented explanation, and an invented
      // explanation in a log is worse than "I don't know", because it ends the
      // reader's search in the wrong place.
      //
      // Give it a moment to settle first (the review step recomputes from
      // auto-saved state), then report the SYMPTOM plus the facts this run
      // actually established, and let the reader diagnose.
      if (await submit.isDisabled()) {
        await settled(page, 10_000);
      }
      if (await submit.isDisabled()) {
        throw new Unreachable(
          `Submit intake is still disabled. Cause not established. Targets this run set: [${
            targetsSet.join(", ") || "none"
          }]; targets it could not find: [${targetsMissing.join(", ") || "none"}]. ` +
            "The button gates on services-picked AND legal-name AND targets-complete; this run did not determine which is unsatisfied.",
        );
      }
      await submit.click();
      if (!(await settled(page))) {
        rec.note(
          "intake submit: the page never went quiet afterwards; downstream steps may be reading a mid-flight state",
        );
      }
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
    // Copy across: a primitive, so the hook cannot see the local's later value.
    if (runState) runState.clientId = clientId;

    if (clientId) {
      await visit(page, rec, "admin", `/admin/queue/${clientId}`);

      const publishOk = await rec.step(
        "admin",
        "publish every requested service for processing",
        "ui",
        async () => {
          // PRECONDITION FIRST. Everything below reads the queue's DOM to
          // decide what happened, so a queue that did not load must stop this
          // step rather than let it report zeros. `IntakeQueue` renders its
          // `<h1>` only on the success path — the error card has no `<h1>` —
          // so this is a state only a loaded queue reaches, not merely "some
          // heading exists".
          const err = await errorCardText(page);
          if (err !== null) {
            throw new Error(
              `the intake queue is showing an error, nothing can be published: ${err.trim().slice(0, 200)}`,
            );
          }
          await affordance(
            page.locator("h1").first(),
            "intake queue <h1> (renders only when the queue loaded)",
            60_000,
          );

          // One "Publish for processing" button per unfulfilled request. Each
          // click re-renders the list, so re-query rather than holding handles.
          let published = 0;
          for (let i = 0; i < SERVICES.length + 2; i += 1) {
            const btn = page
              .getByRole("button", { name: "Publish for processing" })
              .first();
            // A real wait, not a bare `isVisible()`. `isVisible()` returns
            // immediately, so on a still-rendering queue it answers "no" and
            // the loop exits reporting everything published.
            try {
              await btn.waitFor({ state: "visible", timeout: 15_000 });
            } catch {
              break; // none left to publish
            }
            await btn.click();
            if (!(await settled(page))) {
              throw new Indeterminate(
                `published ${published + 1} request(s), then the queue never went quiet — cannot tell how many landed`,
              );
            }
            published += 1;
          }

          if (!(await settled(page))) {
            throw new Indeterminate(
              "the queue never went quiet after publishing — the remaining count would be a guess",
            );
          }
          const left = await page
            .getByRole("button", { name: "Publish for processing" })
            .count();
          rec.note(
            `published ${published} service request(s); unpublished remaining: ${left}`,
          );
          return true;
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
            // Not a throw: the run walks whatever DID open. But the WORDING is
            // load-bearing, and the first draft got it wrong in the most
            // expensive way. "NOT opened by publish" attributes a cause, and
            // that attribution is only available if publishing actually
            // completed. When the publish step did not, the honest sentence
            // names the missing services WITHOUT blaming a step that never ran
            // to completion — otherwise the log reports a product defect
            // ("publishing silently fails to open workspaces") invented out of
            // the instrument's own uncertainty.
            const names = missing.map((m) => m.type).join(", ");
            rec.note(
              publishOk === true
                ? `NOT opened by publish, which completed: ${names}`
                : `absent, cause UNKNOWN — the publish step did not complete, so this is not evidence about publishing: ${names}`,
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
            //
            // A real wait, not a bare `isVisible()`. The button appears only
            // after the upload round-trips, so an immediate read reliably
            // answers "no" — and the old code then fell through to `await
            // extractDone` and blocked for three minutes on a POST that was
            // never going to be sent, reporting the timeout as if the
            // extraction itself had hung.
            const extract = page
              .getByRole("button", { name: "Extract from this" })
              .first();
            try {
              await extract.waitFor({ state: "visible", timeout: 30_000 });
              await extract.click();
              await acknowledgeOfflineAi(page);
            } catch {
              rec.note(
                "tech-debt: no 'Extract from this' button after a 30s wait — the upload may have auto-extracted, or the upload did not land",
              );
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
          // Settle before believing a disabled read: a visible-but-unhydrated
          // button reports disabled, and "React had not attached yet" must not
          // be logged as a product state. The cause is NOT asserted — the first
          // draft blamed "this assessment status" with nothing to support it.
          if (await runAi.isDisabled()) {
            await settled(page, 10_000);
          }
          if (await runAi.isDisabled()) {
            throw new Unreachable(
              `${svc.slug}: Run AI is present but disabled; cause not established`,
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
          if (!(await settled(page))) {
            rec.note(
              `${svc.slug}: the workspace never went quiet after the post-Run-AI reload; the approve step below may be reading a mid-flight page`,
            );
          }
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
          await affordance(approve, `${svc.slug} Approve control`, 60_000);

          // A visible button can still be pre-hydration. Give it a beat before
          // calling it disabled, so "React had not attached yet" is not
          // recorded as "the product disabled this control".
          if (await approve.isDisabled()) {
            await settled(page, 10_000);
          }
          if (await approve.isDisabled()) {
            throw new Unreachable(
              `${svc.slug}: Approve is present but disabled; cause not established`,
            );
          }

          // waitForResponse BEFORE the click — the same pattern Run AI,
          // finalize and release already use in this file, and the reason
          // matters: `waitForLoadState("networkidle")` after a click does not
          // wait for THIS request, so the approve POST could still be in
          // flight when the fallback below reads the status, sees `draft`, and
          // reports that the UI control did not work.
          const approved = page.waitForResponse(
            (r) =>
              r.url().includes("/approve") && r.request().method() === "POST",
            { timeout: 120_000 },
          );
          await approve.click();
          const res = await approved;
          rec.note(`${svc.slug}: approve -> ${res.status()}`);
          return res.ok();
        });

        // The UI Approve is the interesting path; if it did not land, every
        // deliverable step below is unreachable, which is a poor trade for an
        // instrument. Fall back through the API — and say ONLY what is known.
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
              // The wording is the finding, so it must not over-claim. This
              // step cannot see whether the UI step succeeded; the log rows are
              // adjacent and the reader can compare them. Asserting "the UI
              // control did not do it" from a status read that may simply have
              // raced the POST is how an instrument invents a defect.
              rec.note(
                `${svc.slug}: approved via API. Read the preceding "approve the assessment" row for whether the UI control had already done it.`,
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
        // Same settle-then-recheck as Run AI and Approve. The cause is not
        // asserted: `canFinalize` gates on the assessment being approved OR
        // released, but a disabled read here may equally be a pre-hydration
        // one, and this run cannot tell the two apart from the button alone.
        if (await finalize.isDisabled()) {
          await settled(page, 10_000);
        }
        if (await finalize.isDisabled()) {
          throw new Unreachable(
            `${svc.slug}: Finalize is present but disabled; cause not established (it gates on the assessment being approved or released)`,
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
      await visit(page, rec, "Risk-Register", "/admin/risk-register");

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
        // A count is a CLAIM, and "0 download links" is one of the more
        // alarming claims this log can make. It is only worth writing if the
        // page had finished rendering — an unsettled read reports zero for a
        // page that simply had not painted yet.
        if (!(await settled(page))) {
          throw new Indeterminate(
            "/results never went quiet — a download-link count taken now would be a guess, and a low one",
          );
        }
        const err = await errorCardText(page);
        if (err !== null) {
          throw new Error(
            `/results is showing an error, so any link count is meaningless: ${err.trim().slice(0, 200)}`,
          );
        }
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

    // Reached only if the walk ran to the end. The log reports this, so a
    // reader can tell a COMPLETE record from a PARTIAL one — the same
    // ok/indeterminate discipline applied to the log itself. A truncated log
    // that does not say it is truncated invites conclusions from absence.
    if (runState) runState.completed = true;
  } catch (err) {
    // `writeLog` used to live in a `finally` here. It has moved to the
    // `afterEach` hook above, which runs after a TIMEOUT — this block does not.
    //
    // What is left is still worth having: every step in this run is wrapped in
    // `rec.step`, which catches, so nothing should reach here. If something
    // does, it escaped the recorder and would otherwise appear in the log only
    // as an unexplained early stop. Note it, then rethrow so the test still
    // reports as failed.
    rec.note(`run ABORTED outside any recorded step: ${describe(err)}`);
    throw err;
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
    completed: boolean;
  },
): void {
  const ok = rec.steps.filter((s) => s.outcome === "ok").length;
  const failed = rec.steps.filter((s) => s.outcome === "failed").length;
  const missed = rec.steps.filter((s) => s.outcome === "unreachable").length;
  const unknown = rec.steps.filter((s) => s.outcome === "indeterminate").length;

  const lines: string[] = [];
  lines.push(`# Full-engagement observation run — ${RUN_STAMP}`);
  lines.push("");
  if (!ctx.completed) {
    // First line in the file, before anything a reader might reason from. A
    // truncated log that does not say it is truncated invites conclusions
    // drawn from absence — "ATT&CK is missing" reads as a finding when it only
    // means the run stopped before ATT&CK.
    lines.push(
      "> **PARTIAL RECORD — this run did NOT reach the end of the walk.**",
    );
    lines.push(
      "> It timed out, threw, or was interrupted. Anything absent below is absent",
    );
    lines.push(
      "> because the run stopped, NOT because the product lacks it. Draw no",
    );
    lines.push("> conclusions from what is missing.");
    lines.push("");
  }
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
  lines.push(`- ok — looked, it was fine: ${ok}`);
  lines.push(`- failed — looked, it went wrong: ${failed}`);
  lines.push(`- unreachable — looked, it was not there: ${missed}`);
  lines.push(`- indeterminate — COULD NOT LOOK, no claim made: ${unknown}`);
  lines.push("");
  lines.push(
    "Read `indeterminate` as a statement about this run, not about the product.",
  );
  lines.push(
    "It means a page never settled or a read raced the render, so nothing was",
  );
  lines.push(
    "concluded. Every downstream row after one is suspect for the same reason —",
  );
  lines.push(
    "an earlier draft of this file recorded such reads as `ok` and thereby",
  );
  lines.push("reported a product defect that did not exist.");
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
  lines.push(
    "Rows are in COMPLETION order, and `#` is the row's position. A step that",
  );
  lines.push(
    "contains others therefore appears AFTER them — the per-artifact downloads",
  );
  lines.push(
    'are nested inside "read the released deliverable", so they are listed first.',
  );
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
        summary: {
          total: rec.steps.length,
          ok,
          failed,
          unreachable: missed,
          indeterminate: unknown,
        },
        engagement: {
          legalName: ctx.legalName,
          clientEmail: ctx.clientEmail,
          clientId: ctx.clientId,
          services: Object.fromEntries(ctx.serviceIds),
        },
        videoPath: ctx.videoPath,
        outputDir: ctx.outputDir,
        // False means the walk stopped early: absence below is the run's, not
        // the product's. Machine-readable twin of the banner in the Markdown.
        completed: ctx.completed,
        stepOrder: "completion",
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
    `\nfull-engagement: ${ok} ok, ${failed} failed, ${missed} unreachable, ${unknown} indeterminate — ${RUN_DIR}\n`,
  );
}
