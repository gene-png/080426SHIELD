import fs from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import { ADMIN_EMAIL, ADMIN_PASSWORD, register, signIn } from "../helpers/auth";
import { acknowledgeOfflineAi } from "../helpers/ai";
import { assertAiMode, intendedAiMode } from "../helpers/aiModeGate";

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
 * **THE RULE IS A SHAPE, NOT A LIST OF METHODS — and the first version of this
 * paragraph got that wrong, in the header of the fix for getting it wrong.**
 *
 * It read "never a bare `isVisible()`/`count()`", naming two methods. Playwright
 * has many non-waiting reads, and the ones the sentence omitted are what broke
 * the first real run: `isChecked()` on the intake checkboxes, read twice without
 * waiting, reported "would not stay checked after two clicks" about a box that
 * had in fact been selected — and that single racy read cascaded into three
 * services never opened, no deliverable, no Risk Register, and eleven downstream
 * rows. Enumerating methods instead of stating the shape is the same
 * enumerate-versus-derive defect this file records everywhere else.
 *
 * The shape: **any read that returns immediately, whose result decides a
 * recorded outcome, is a defect unless something waits first.** Not a method
 * list — a property of the call.
 *
 * **The set is PLAYWRIGHT'S, not ours to curate.** Its API is already split in
 * two along exactly this line: auto-waiting ASSERTIONS poll until they pass
 * (`expect(locator).toBeChecked()`), and IMMEDIATE GETTERS read one instant and
 * never wait (`isChecked`, `isDisabled`, `isVisible`, `isEnabled`, `isEditable`,
 * `isHidden`, `count`, `textContent`, `innerText`, `inputValue`,
 * `getAttribute`). Deriving from that boundary is why the set is closed;
 * listing the ones someone thought of is what failed.
 *
 * **And it is GATED rather than worded**, because a rule in prose gets followed
 * on the line you are thinking about and skipped on the line next to it — which
 * is measured here, not asserted: the wording above named two methods and the
 * two it omitted broke the first real run.
 *
 *     node e2e/scripts/check-immediate-reads.mjs e2e/engagement
 *
 * Report-only. It never fails a run — a blocking gate whose cheapest route to
 * green is deleting the check steers the author into the defect. Legitimate
 * immediate reads carry `// immediate-read: <reason>`; every one in this file
 * does, and each reason says why WAITING would be wrong there. Run it AFTER
 * prettier: waiver association is adjacency, so it is not stable under
 * reformatting, and that has already bitten once.
 *
 * So, when editing this file: anything that decides a step's outcome waits
 * first — `affordance()`, `settled()`, or a poll that reports what it could not
 * establish — and where it cannot, it records `Indeterminate` rather than `ok`
 * and rather than a specific cause invented to explain a symptom. Prefer a
 * driver that WAITS FOR THE TARGET STATE (`driveCheckboxOn`) over one that acts
 * and re-reads. `visit()` does not treat
 * "some heading exists" as arrival, because the error card is a heading — and
 * on the five CLIENT DASHBOARDS the gated and failed states each render an
 * `<h1>` of their own, so even "an `<h1>` exists" is not arrival there.
 *
 * **And when you widen a probe, enumerate what it matches instead of asserting
 * a shape.** The version of `pageState` before this one called itself "a
 * PREDICATE ... so a new error surface is caught without an edit". That was
 * true of the eight admin surfaces it was derived from and false of the five
 * client dashboards, which are the entire subject of Phase 5 — it recorded
 * `ok` over a client who could see nothing. Its `[role="alert"]` half was
 * broader still: 59 sites across 42 files, most of them healthy-page notices,
 * one of which this run triggers by design. A docstring generalising from half
 * the app is the mechanism, not carelessness; the fix is to write down the
 * enumeration and the grep that produced it.
 *
 * ## It carries a workaround for an OPEN defect, and says so every run
 *
 * The intake wizard auto-saves, and advancing a step before the save lands
 * loses the typed value — measured across three runs, where runs 2 and 3
 * stored the email-domain fallback instead of the legal name. **#252.** This
 * spec waits on `SaveStatus` reporting "Saved" before advancing.
 *
 * That wait makes everything downstream measurable, and it also HIDES #252
 * from every future run. So it is RECORDED: each wait reports whether it
 * actually did work, and the step log carries a "Workarounds in force" section
 * directly under the verdict. A clean run that depended on a workaround must
 * not read like a clean run that did not — and when #252 is fixed, the log
 * starts saying "not needed" on its own instead of waiting for someone to
 * think to check.
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
 * 1. **Video** at 1920x1080 — the whole flow, one continuous recording,
 *    because the whole flow is ONE test sharing ONE browser context. Saved
 *    into the run folder by `afterAll`; `recording.md` there says whether the
 *    save worked.
 * 2. **Trace** — a DOM snapshot per action plus the network calls behind each
 *    screen, so when a number looks wrong you can tell whether the API or the
 *    renderer produced it. Playwright writes it after every hook in this file
 *    has run, so `e2e/scripts/run-engagement.sh` preserves it once the runner
 *    exits. **Launch through that script**, or the trace stays in
 *    `test-results/` and the next run deletes it.
 * 3. **Every generated artifact**, downloaded into a dated folder under
 *    `e2e/artifacts/`, named by SERVICE and CLIENT. A video shows the click that
 *    produced a deliverable; it does not show what is inside it.
 *
 * Video, trace and the 1920x1080 viewport are set HERE at the spec level, never
 * in `e2e/playwright.config.ts`. Verified against that file: it sets
 * `trace: "on-first-retry"`, no video at all, and a chromium project that
 * spreads `devices["Desktop Chrome"]` (1280x720) — so raising any of the three
 * globally would slow every existing spec, re-lay-out the ones that assert
 * rendered geometry, and change CI's E2E job. `test.use` overrides the project
 * `use` block for this file only.
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

test.use({
  video: { mode: "on", size: { width: 1920, height: 1080 } },
  trace: "on",
  // 1920x1080, set HERE rather than in `e2e/playwright.config.ts`.
  //
  // The config's chromium project spreads `devices["Desktop Chrome"]`, whose
  // viewport is 1280x720 -- so without this the recording is 720p and the
  // demonstration is shot at the wrong size. Raising it in the config instead
  // would re-lay-out all 43 smoke specs, several of which assert rendered
  // geometry, and change CI's E2E job. Same reasoning the video/trace lines
  // already carry.
  //
  // `video.size` is set explicitly too: it defaults to a scaled-down fit of
  // the viewport rather than matching it, so a 1920x1080 viewport alone does
  // not produce a 1920x1080 file.
  viewport: { width: 1920, height: 1080 },
});

// One continuous walk of the whole product. Generous, and deliberately not
// `test.slow()` (which only triples the 90s project timeout).
const RUN_BUDGET_MS = 45 * 60_000;

/**
 * How long to wait for a CONTROL on a page that has already loaded.
 *
 * Measured on the first real run: five absent controls waited 60s each and
 * accounted for 310 of the run's 672 seconds — 46% of the wall clock spent
 * confirming that buttons which were never going to appear had not appeared. A
 * control on a settled page is present in milliseconds or it is absent.
 *
 * **Do not read the saving as headroom.** Most of the gap to `RUN_BUDGET_MS` on
 * that run was work that did not happen: eleven steps were skipped downstream of
 * one racy read. When those do real work the run grows, and it grows in the slow
 * places — Run-AI, finalize, release, the register.
 *
 * PAGE LANDMARKS after a fresh navigation keep their longer waits: `next dev`
 * compiles a route on first hit, and CLAUDE.md records cold-compile timeouts as
 * a known flake. This constant is for controls, not for arrival.
 */
const CONTROL_WAIT_MS = 10_000;

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

const ARTIFACT_ROOT = path.resolve(__dirname, "..", "artifacts");

/**
 * The run folder. NOT a `const`, because the stamp is module scope and a RETRY
 * is not.
 *
 * `playwright.config.ts` sets `retries: 1` when `CI` is set. A retry re-enters
 * the test and reassigns `runState`, but `RUN_STAMP` is computed once at module
 * load — so both attempts resolve the same folder and the retry's `step-log.md`
 * silently overwrites the failed attempt's. The failed attempt is the one worth
 * reading.
 *
 * Suffixed per attempt instead. Low likelihood — this spec is opt-in and CI
 * never sets its flag — but the cost of being wrong is losing exactly the
 * record this instrument exists to produce.
 */
let RUN_DIR = path.join(ARTIFACT_ROOT, `engagement-${RUN_STAMP}`);

/** Point `RUN_DIR` at this attempt's folder. Called once, at test start. */
function resolveRunDir(retry: number): void {
  RUN_DIR = path.join(
    ARTIFACT_ROOT,
    retry > 0
      ? `engagement-${RUN_STAMP}-retry${retry}`
      : `engagement-${RUN_STAMP}`,
  );
}

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
  /**
   * Workarounds this run has in force for a KNOWN OPEN DEFECT, and whether
   * each was actually needed.
   *
   * A workaround that disappears into passing behaviour is how a known defect
   * stops being known: every future run comes back clean, and the cleanliness
   * silently depends on a wait nobody can see. So the log names the issue, and
   * records whether the workaround did any work — if the underlying defect is
   * ever fixed, `needed: false` starts appearing and somebody learns something.
   * A silent workaround teaches nobody, forever.
   */
  readonly workarounds: Array<{
    ref: string;
    needed: boolean;
    detail: string;
  }> = [];

  /** Record that a workaround for `ref` was applied, and whether it did work. */
  workaround(ref: string, needed: boolean, detail: string): void {
    this.workarounds.push({ ref, needed, detail });
    // eslint-disable-next-line no-console
    console.log(
      `      w/a   ${ref} ${needed ? "NEEDED" : "not needed"} — ${detail}`,
    );
  }

  /**
   * Steps ENTERED but not yet completed, outermost first. Non-empty when the
   * run was abandoned mid-step — `writeLog` reports it as the in-flight chain.
   */
  readonly inFlight: Array<{
    phase: string;
    name: string;
    via: Via;
    started: number;
  }> = [];
  private seq = 0;

  /** The most recently recorded row, for a caller pairing two observations. */
  lastStep(): StepRecord | undefined {
    return this.steps[this.steps.length - 1];
  }

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

    // ENTRY MARKER. Observed on the way IN, and it is the only record a step
    // that HANGS will ever produce.
    //
    // On a test timeout Playwright abandons the body mid-`await`, so the
    // in-flight step's own `try`/`catch` never runs and it pushes no row. The
    // log then arrives with the PARTIAL banner and no row naming the step that
    // consumed the budget — on a forty-step walk carrying 240s and 300s waits,
    // the single most valuable datum in the file, missing.
    //
    // A STACK rather than one slot, because steps nest: the per-artifact
    // downloads run inside "read the released deliverable", and reporting only
    // the innermost would lose which service it belonged to.
    //
    // This is not a success record, so "write the success record where the
    // success is" does not bar it — it asserts only that the step was ENTERED,
    // which is true at the moment it is written. The outcome is still recorded
    // exclusively in the completion branches below.
    this.inFlight.push({ phase, name, via, started });
    // eslint-disable-next-line no-console
    console.log(`  ...   [${phase}] ${name} (${via}) ENTERED`);

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
      this.inFlight.pop();
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
      this.inFlight.pop();
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
 * ## `visible` is a CHOICE, and it was the wrong one once
 *
 * The wait state is a parameter rather than a constant because "visible" is
 * not always the right question, and asking it of a control that can never be
 * visible produces a check that cannot pass -- reported, like every miss here
 * used to be, in the vocabulary of a product failure.
 *
 * `Dropzone`'s `<input type="file">` carries Tailwind `hidden`
 * (`display: none`) by design; the drop target is the visible affordance and
 * `setInputFiles` drives the input regardless. Waiting for `visible` cost
 * three runs of Tech Debt, and everything downstream of its upload with it.
 *
 * Swept rather than assumed: `className="hidden"` appears once in
 * `apps/web/src/components`, in `Dropzone`. Every other structurally-hidden
 * control there is `sr-only`, which keeps a bounding box and which Playwright
 * therefore treats as visible. Of the five `affordance` call sites in this
 * file, that file input is the only one whose target is `display: none`.
 *
 * The message names the state it waited for, so a future miss says which
 * question was asked and not merely that the answer was no.
 *
 * Deliberately NOT fixed by adding `.first()` to the ambiguous call sites
 * (`Release to client`, `Yes, release`, `Export XLSX / PDF / Word`,
 * `/^(Generate|Regenerate)$/`). `.first()` would silently pick one of two
 * buttons and record `ok` — it hides exactly the defect this instrument exists
 * to surface. They stay strict, and a duplicate now reports itself accurately.
 */
/**
 * The needle a failed search was looking for, in the message about the failure.
 *
 * A MISS is the one outcome whose message could not previously be acted on. It
 * said "affordance never appeared", which reads as a statement about the PAGE
 * and is indistinguishable from the product failing to render the control --
 * so a locator naming something the product does not call it produced a
 * confident, specific, wrong sentence, and the instrument's own defect and the
 * product's defect rendered identically. That cost four runs.
 *
 * The strict-mode branch above already gets this right for free: Playwright
 * reports "resolved to 2 elements" and quotes both, which is why an ambiguous
 * locator has always been diagnosable here in one read while a miss was not.
 * `Locator.toString()` is the same evidence for the other direction -- it
 * yields the resolved selector (`internal:role=button[name=/^(Finalize)$/]`),
 * which is the needle, not the human label the caller happened to choose.
 *
 * Wrapped because `toString` is not part of the documented Locator surface and
 * a future Playwright could change or drop it. Losing the needle must not turn
 * a real MISS into a crash, so a throw here degrades to the old message rather
 * than propagating -- the ONE place in this file where swallowing is correct,
 * because the thing being swallowed is the diagnostic and not the result.
 */
function needle(loc: Locator): string {
  try {
    return String(loc).replace(/\s+/g, " ").slice(0, 200);
  } catch {
    return "<locator would not describe itself>";
  }
}

async function affordance(
  loc: Locator,
  label: string,
  timeout = CONTROL_WAIT_MS,
  state: "visible" | "attached" = "visible",
): Promise<Locator> {
  try {
    await loc.waitFor({ state, timeout });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const name = err instanceof Error ? err.name : "";
    if (/has been closed|Target crashed/i.test(message)) {
      throw new Indeterminate(
        `could not look for ${label} (${needle(loc)}): ${message.split("\n")[0]}`,
      );
    }
    if (name === "TimeoutError") {
      throw new Unreachable(
        `affordance never became ${state} within ${timeout}ms: ${label} — searched for ${needle(loc)}`,
      );
    }
    throw err;
  }
  return loc;
}

/**
 * Wait for an admin workspace to MOUNT its workflow, and name what is blocking
 * it when it does not.
 *
 * ## Why this exists
 *
 * The 2026-09-09 18:11 run reported ATT&CK's Run AI as
 * `affordance never became visible within 10000ms`. That was accurate and
 * useless: the button was not hidden, not disabled, and not late — **it was
 * not mounted**.
 *
 * `AttackWorkspace` renders a three-way ternary inside its single JSX return:
 *
 *     !catalog   ? "Loading ATT&CK matrix…"
 *   : !assessment ? <EmptyState "No coverage assessment yet" />
 *   :               <WorkflowStep 1..4>   // Run AI lives in here
 *
 * so WorkflowStep 1 through 4 do not exist in the DOM until BOTH `catalog` and
 * `assessment` state resolve — from two **sequential** fetches fired on mount,
 * followed by the heatmap. The step reloads the page immediately before
 * looking, so it pays that whole chain every time, and 10s did not cover it
 * while the API was still busy.
 *
 * There is no early `return` to grep for, which is why reading the file for
 * one found nothing. The gate is a conditional expression, not a statement.
 *
 * ## Why it reports the blocker rather than just waiting longer
 *
 * A longer timeout would have made the run pass and taught nobody anything.
 * The two placeholders are the two halves of the mount, and which one is on
 * screen says which fetch has not come back — so a MISS here names the gate
 * instead of naming the button. "Still fetching the catalog" and "no
 * assessment resolved" send you to different places; "button not visible"
 * sends you to the button, which was never the problem.
 *
 * CSF is included because its mount has a second gate of its own: `Run AI
 * (csf_score)` does not exist until Working Profiles are seeded, so a mounted
 * CSF workspace shows `Seed Working Profiles` and no Run AI at all. Treating
 * that as "mounted" is correct — the workflow IS up; the run just has a step
 * to perform before the button exists.
 */
const MOUNT_WAIT_MS = 90_000;

async function workspaceMounted(page: Page, slug: string): Promise<void> {
  const runAi = page.getByRole("button", { name: /^Run AI\b/ });
  const seedProfiles = page.getByRole("button", {
    name: "Seed Working Profiles",
  });
  const loadingMatrix = page.getByText(/Loading ATT&CK matrix/i);
  const noAssessment = page.getByText(/No coverage assessment yet/i);

  const deadline = Date.now() + MOUNT_WAIT_MS;
  let blocker = "nothing on screen named a cause";
  while (Date.now() < deadline) {
    // Either control means the workflow mounted. Count, not visibility: this
    // asks whether the node EXISTS, which is the thing the ternary decides.
    if ((await runAi.count()) > 0 || (await seedProfiles.count()) > 0) return;
    if (await loadingMatrix.isVisible().catch(() => false)) {
      blocker =
        'still fetching the catalog — "Loading ATT&CK matrix…" is on screen';
    } else if (await noAssessment.isVisible().catch(() => false)) {
      blocker =
        'no assessment resolved — "No coverage assessment yet" is on screen';
    }
    await page.waitForTimeout(500);
  }
  throw new Unreachable(
    `${slug}: the workspace never mounted its workflow within ${MOUNT_WAIT_MS}ms — ${blocker}. ` +
      `Neither a Run AI control nor "Seed Working Profiles" ever entered the DOM, so the step could not begin.`,
  );
}

/**
 * Compile-time exhaustiveness.
 *
 * `value: never` only type-checks when every member of a union has already
 * been handled, so adding one and forgetting a branch is a BUILD failure
 * rather than a silent fall-through into whichever branch happens to be last.
 *
 * This is the same move as the verdict's `Record<Outcome, ...>`, and it is
 * worth naming why it works there and not everywhere: both cover CLOSED SETS
 * THIS FILE OWNS. Where the set belongs to somebody else — Playwright's
 * `Locator` methods, say — no type can make a member unavailable, and a gate
 * is the only instrument left.
 */
function assertNever(value: never, context: string): never {
  throw new Error(`${context}: unhandled variant ${JSON.stringify(value)}`);
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
 * What state is this page in?
 *
 * ## The scope, ENUMERATED — this app has TWO error idioms, not one
 *
 * The previous version of this claimed to be "a PREDICATE over that shape
 * rather than enumerated per page, so a new error surface is caught without an
 * edit". That sentence was true of the surfaces it was derived from and false
 * of the whole app, and asserting it over everything produced two live
 * defects. What follows is what the probes ACTUALLY match, per idiom.
 *
 * **Idiom 1 — the admin/intake error card.** A `CardTitle`, which renders an
 * `<h3>`, reading "Couldn't load ...". Matched by the heading probe.
 *
 *     grep -rn "Couldn&apos;t load" --include=*.tsx apps/web/src
 *
 * Covers IntakeQueue, CsfWorkspace, ZtWorkspace, AttackWorkspace,
 * TechDebtWorkspace, AssessmentsView, IntakeWizard, and both self-assessments.
 *
 * **Idiom 2 — the CLIENT DASHBOARD gate, which the card probe cannot see.**
 * All five client dashboards (`csf`, `zt`, `attack`, `tech-debt`, `risk`)
 * render an `<h1>` "... not available yet" with the discriminating sentence in
 * a sibling `<p>`. There is no "Couldn't load" HEADING anywhere on them, so
 * idiom 1's probe returns nothing and the `<h1>` resolves — which is how five
 * dashboards a client cannot see were recorded `ok`. Worse, that `<h1>` is
 * byte-identical whether the report was never released or the fetch failed, so
 * the heading alone cannot separate them. Hence `notAvailable()` below reads
 * the `<p>`.
 *
 * ## Why there is no generic `[role="alert"]` probe any more
 *
 * There was, and it manufactured a finding. `role="alert"` is this app's
 * general announcement mechanism, not its load-failure surface:
 *
 *     grep -rn 'role="alert"' --include=*.tsx apps/web/src | grep -v '\.test\.'
 *
 * returns 59 sites across 42 files — form validation, save errors, session
 * warnings, MFA enrolment, and accounting notices on healthy pages. The one
 * that bites this run is `AttackCitationAccounting`, which renders an alert
 * whenever `rejected > 0` ("N citations named tools that are not on the list
 * and were dropped"). This run does ATT&CK Run-AI before the Tech Debt list is
 * approved, so rejections are expected, and Phase 6 re-visits that workspace —
 * the old probe would have read a designed notice on a working page and
 * recorded `failed`.
 *
 * The probe is now TEXT-SCOPED to the load-failure copy ("Failed to load ...",
 * "Couldn't load ..."), which is what `DeliverablesTable` renders and what the
 * s40 incident in CLAUDE.md was about. Narrowing rather than deleting keeps
 * that case; the scope is the copy, not the role.
 *
 * ## On the bare `isVisible()` calls below
 *
 * Deliberate, and the only ones in this file. This is an "is X on screen RIGHT
 * NOW" probe, not a decision about arrival. Waiting would invert its meaning: a
 * `waitFor` on an error card would sit for the full timeout on every healthy
 * page and then report no error. A `loaded` result is never treated as proof of
 * health — the CALLER still establishes arrival positively afterwards — so this
 * function may return a false negative and nothing downstream depends on it not
 * doing so.
 */
type PageState =
  | { kind: "loaded" }
  | { kind: "load-error"; text: string }
  | {
      kind: "not-available";
      heading: string;
      /**
       * `gated`       — the report has not been released/finalized yet.
       * `load-failed` — the dashboard fetch failed.
       * `unknown`     — the copy matched neither; do NOT guess which.
       */
      reason: "gated" | "load-failed" | "unknown";
      detail: string;
    };

async function pageState(page: Page): Promise<PageState> {
  // Idiom 1: the admin/intake error card.
  const card = page.getByRole("heading", { name: /Couldn.t load/i }).first();
  // immediate-read: point-in-time probe. Waiting would INVERT its meaning — a
  // wait on an error card sits for the full timeout on every healthy page. A
  // null result is never treated as proof of health; the caller establishes
  // arrival positively afterwards.
  if (await card.isVisible().catch(() => false)) {
    return {
      kind: "load-error",
      // immediate-read: point-in-time probe. Waiting would INVERT its meaning
      // — a wait on an error card sits for the full timeout on every healthy
      // page. A null result is never treated as proof of health; the caller
      // establishes arrival positively afterwards.
      text: (await card.textContent().catch(() => null)) ?? "Couldn't load (…)",
    };
  }

  // Idiom 2: the client-dashboard gate. Covers both wordings — the four
  // service dashboards say "Dashboard not available yet", the Risk Register
  // says "Risk Register not available yet".
  const gate = page
    .getByRole("heading", { name: /not available yet\s*$/i })
    .first();
  // immediate-read: point-in-time probe. Waiting would INVERT its meaning — a
  // wait on an error card sits for the full timeout on every healthy page. A
  // null result is never treated as proof of health; the caller establishes
  // arrival positively afterwards.
  if (await gate.isVisible().catch(() => false)) {
    // immediate-read: point-in-time probe. Waiting would INVERT its meaning —
    // a wait on an error card sits for the full timeout on every healthy page.
    // A null result is never treated as proof of health; the caller
    // establishes arrival positively afterwards.
    const rawHeading = await gate.textContent().catch(() => null);
    const heading = (rawHeading ?? "not available yet").trim();
    // The discriminating sentence is in a sibling <p>, so read the region
    // rather than the heading. Reading the heading alone is what made these
    // two states indistinguishable.
    // immediate-read: point-in-time probe; the gate above already established
    // the region is rendered, and waiting on its text would sit for the full
    // timeout on every page that has no error to report.
    const main = page.locator("main").first();
    // immediate-read: point-in-time probe. Waiting would INVERT its meaning —
    // a wait on an error card sits for the full timeout on every healthy
    // page. A null result is never treated as proof of health; the caller
    // establishes arrival positively afterwards.
    const body = (await main.textContent().catch(() => null)) ?? "";
    const reason = /hasn.t been (released|finalized)/i.test(body)
      ? "gated"
      : /We couldn.t load/i.test(body)
        ? "load-failed"
        : "unknown";
    return {
      kind: "not-available",
      heading,
      reason,
      detail: body.trim().slice(0, 300),
    };
  }

  // Text-scoped inline load failure. NOT a bare `role="alert"` — see above.
  const alert = page
    .getByRole("alert")
    .filter({ hasText: /(Failed|Unable) to load|Couldn.t load/i })
    .first();
  // immediate-read: point-in-time probe. Waiting would INVERT its meaning — a
  // wait on an error card sits for the full timeout on every healthy page. A
  // null result is never treated as proof of health; the caller establishes
  // arrival positively afterwards.
  if (await alert.isVisible().catch(() => false)) {
    return {
      kind: "load-error",
      text:
        // immediate-read: point-in-time probe. Waiting would INVERT its
        // meaning — a wait on an error card sits for the full timeout on
        // every healthy page. A null result is never treated as proof of
        // health; the caller establishes arrival positively afterwards.
        (await alert.textContent().catch(() => null)) ?? "[load-failure alert]",
    };
  }

  return { kind: "loaded" };
}

/**
 * Wait for the intake wizard's AUTO-SAVE to land before advancing a step.
 *
 * ## Why this exists, and why it is recorded rather than done quietly
 *
 * The wizard auto-saves on change and `SaveStatus` reports the state
 * ("Saving…" / "Saved" / "Couldn't save: …"). Filling a field and clicking
 * "Next →" immediately races that save. Measured across three runs of
 * unchanged product code: run 1 stored the typed legal name, runs 2 and 3
 * stored the email-domain fallback instead — the save had not landed when the
 * step advanced. **Tracked as #252.**
 *
 * Run 1 was not a counter-example, it was a control: its service-selection
 * loop aborted on the first checkbox, so it performed a fraction of the
 * interactions before reaching Submit. Fixing that loop is what made this race
 * reachable on every run — one defect had been masking another.
 *
 * **This is a workaround for an open defect, and it is recorded as one.** A
 * workaround that vanishes into passing behaviour is how a known defect stops
 * being known: every later run reads clean, and the cleanliness quietly
 * depends on a wait nobody can see. So each call records to `rec.workarounds`
 * whether the wait ACTUALLY DID WORK — if the save was already landed, that is
 * evidence the race is gone, and `not needed` starts appearing in the log.
 *
 * Deliberately NOT worked around any other way. Resolving the tenant by its
 * fallback name, or by id from another source, would turn the run green while
 * making the instrument blind to exactly the class of defect it exists to
 * catch.
 */
async function waitForIntakeSave(
  page: Page,
  rec: Recorder,
  after: string,
): Promise<void> {
  const started = Date.now();
  const saved = page.getByText(/^Saved\b/).first();
  try {
    await saved.waitFor({ state: "visible", timeout: 15_000 });
  } catch {
    // Distinguish "the app said it could not save" from "nothing ever
    // reported". `SaveStatus` renders the failure as its own message, and
    // conflating the two would report a product error as an instrument
    // timeout.
    const saveError = page.getByText(/^Couldn.t save/).first();
    // immediate-read: only reached after the wait above already timed out, so
    // there is nothing left to wait for; this reads which of two terminal
    // states the page settled into.
    const errText = await saveError.textContent().catch(() => null);
    if (errText !== null) {
      throw new Error(`intake auto-save FAILED after ${after}: ${errText}`);
    }
    throw new Indeterminate(
      `intake auto-save never reported "Saved" within 15s after ${after} — cannot tell whether the value persisted`,
    );
  }
  const waitedMs = Date.now() - started;
  // Under ~400ms means the save had effectively already landed and the wait
  // did no work. That is the signal worth watching: when #252 is fixed this
  // flips to "not needed" and the log says so on its own.
  const needed = waitedMs >= 400;
  rec.workaround(
    "#252",
    needed,
    `waited ${waitedMs}ms for the intake auto-save after ${after}` +
      (needed
        ? " — the save had NOT landed when the step was ready to advance"
        : " — the save had already landed; this wait did no work"),
  );
}

/**
 * Sign out, and confirm it by the PRIMARY NAV's "Sign in" link specifically.
 *
 * `helpers/auth.signOut` waits on a bare `getByRole("link", { name: "Sign in" })`,
 * which is ambiguous on the signed-out home page: `site/PublicHeader.tsx`
 * renders one inside `<nav aria-label="Primary">` and `marketing/Hero.tsx`
 * renders a second as its CTA. Both are real and both are correct — this run
 * lands on `/` after signing out, so it meets both, and all three sign-outs
 * failed on the first real run with a strict-mode violation.
 *
 * Scoped to the nav landmark rather than `.first()`, for the reason `.first()`
 * is refused everywhere else in this file: it would have picked one of the two
 * arbitrarily and recorded `ok`, and the ambiguity is exactly what the strict
 * locator surfaced. The nav link is the one that means "the session ended".
 *
 * ## Why the shared helper is left alone, deliberately
 *
 * `helpers/auth.ts` carries the same latent ambiguity, and fixing it there
 * would be the better fix for the repo — but that helper is used by the whole
 * smoke suite, so changing it puts ~40 CI-gating specs at risk to serve one
 * opt-in instrument. Those specs sign out from pages with no marketing Hero,
 * which is why the ambiguity has stayed latent for them. Worth filing; not
 * worth this branch changing under them. Stated here so the duplication reads
 * as a choice rather than as someone not noticing the helper existed.
 */
async function signOutViaNav(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Sign out" }).click();
  await affordance(
    page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link", { name: "Sign in" }),
    "the primary nav's Sign in link (proof the session ended)",
    20_000,
  );
}

/**
 * Poll a checkbox until it reads CHECKED, or give up and say so.
 *
 * `isChecked()` returns immediately. That is what broke the first real run:
 * the box was read, clicked, re-read while React was still re-rendering, read
 * false, clicked AGAIN — toggling it back off — and reported "would not stay
 * checked after two clicks". The click had worked; the reading had not.
 *
 * So: click at most once per attempt, then WAIT for the state to arrive rather
 * than re-reading straight away. A second attempt covers the case where the
 * very first read was itself pre-hydration and the click therefore turned an
 * already-on box off.
 *
 * Returns "checked", or a description of what could not be established — never
 * a claim about the product. The caller records `indeterminate`.
 */
async function driveCheckboxOn(box: Locator): Promise<string> {
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    // immediate-read: this IS the poll. The read must be instantaneous by
    // construction; the waiting is the surrounding loop, which reports what
    // it could not establish rather than claiming a state.
    if (await box.isChecked().catch(() => false)) return "checked";
    await box.click();
    // The wait is the fix. 10s is generous for a local React re-render and
    // costs nothing on the happy path, which resolves on the first poll.
    const deadline = Date.now() + 10_000;
    for (;;) {
      // immediate-read: this IS the poll. The read must be instantaneous by
      // construction; the waiting is the surrounding loop, which reports what
      // it could not establish rather than claiming a state.
      if (await box.isChecked().catch(() => false)) return "checked";
      if (Date.now() >= deadline) break;
      await box.page().waitForTimeout(200);
    }
    if (attempt === 1) {
      // The click may have turned an already-checked box OFF (a pre-hydration
      // first read). Loop once more; the next click puts it back on.
      continue;
    }
  }
  return "never read as checked within 10s of either of two clicks";
}

/**
 * Did we actually land on the page we asked for, as the identity we assumed?
 *
 * `visit()` used to capture the `goto` status into a variable that appeared
 * only inside message strings — it decided nothing. The verdict was "no error
 * card, and some `<h1>` exists", and TWO `<h1>`s in this app mean the opposite
 * of arrival:
 *
 *  - `app/admin/layout.tsx` renders `<h1>Not authorized</h1>` for an
 *    authenticated NON-admin.
 *  - `app/sign-in/page.tsx` renders `<h1>Sign in</h1>`, and that page does not
 *    redirect an already-signed-in user, so a bounce there is a real 200 with
 *    a real `<h1>`.
 *
 * The constructible failure: Phase 6's "admin signs back in" records `failed`
 * and the run continues by design, after which all eight `adminPages` visits
 * land on `/sign-in` or the Not-authorized shell and every one records `ok`.
 * One `failed` row, eight rows earlier, against eight confident `ok`s.
 *
 * Returns null when nothing is wrong. `status` comes from `goto`, which is
 * null for a client-side navigation.
 */
function landingProblem(
  page: Page,
  target: string,
  status: number | null,
  h1: string | null,
): { fatal: boolean; message: string } | null {
  if (status !== null && status >= 400) {
    return { fatal: true, message: `HTTP ${status}` };
  }
  const here = new URL(page.url()).pathname;
  const wanted = new URL(target, page.url()).pathname;
  if (here.startsWith("/sign-in") && !wanted.startsWith("/sign-in")) {
    return {
      // Not `fatal`: this says the SESSION is not what the phase assumed, which
      // makes every reading off this page meaningless rather than wrong. It is
      // an "I could not look", so it records `indeterminate`.
      fatal: false,
      message: `bounced to ${here} — the session is not what this phase assumed, so nothing here describes ${wanted}`,
    };
  }
  if (h1 !== null && /^\s*Not authorized\s*$/.test(h1)) {
    return {
      fatal: true,
      message: `the admin shell rendered "Not authorized" — this session is authenticated but not a Kentro consultant`,
    };
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
 * For the ADMIN surfaces a real discriminator is available: on success they
 * render an `<h1>`, and the error card renders no `<h1>` at all. The CLIENT
 * DASHBOARDS are the case that breaks: they render an `<h1>` on the gated and
 * failed paths too, so "an `<h1>` exists" is not arrival there either. See
 * `pageState`, which separates the two idioms.
 *
 *  - load error (either idiom)   -> `failed`, quoting what it said.
 *  - "not available yet" + gated -> `unreachable`. Looked; the content is not
 *                                   there. NOT `ok` — a client seeing this for
 *                                   a released report is the #114/#207 defect
 *                                   this whole crossing exists to catch.
 *  - "not available yet" + fetch failed -> `failed`.
 *  - "not available yet" + copy unrecognised -> `indeterminate`; do not guess
 *                                   which branch rendered.
 *  - `<h1>` present              -> `ok`, recording its text.
 *  - no `<h1>`, network settled  -> `ok` with a note (some pages have no `<h1>`;
 *                                   that is not a fault).
 *  - no `<h1>`, never settled    -> `indeterminate`. No claim is made.
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

    // BEFORE anything is read off the page: are we even on it, as the identity
    // this phase assumed? The status is a verdict here, not decoration.
    const earlyH1 = await page
      .locator("h1")
      .first()
      // immediate-read: preceded by settled(), and the timeout argument waits
      // for the element to attach. Recorded as an observation; the landing
      // verdict comes from the HTTP status and the pathname, not from this
      // text alone.
      .textContent({ timeout: 5_000 })
      .catch(() => null);
    const landing = landingProblem(page, url, status, earlyH1);
    if (landing) {
      if (landing.fatal) {
        throw new Error(`${url}: ${landing.message}`);
      }
      throw new Indeterminate(`${url}: ${landing.message}`);
    }

    const state = await pageState(page);
    // EXHAUSTIVE. The chain below used to fall through to "loaded" for any
    // unhandled kind, so a page state added later would have been recorded
    // `ok` — silently, and specifically for a state added because it needed
    // handling. Same defect the verdict's two hand-written sums had: a new
    // member vanishing into the safe-looking branch. `assertNever` makes it a
    // compile error instead.
    if (
      state.kind !== "load-error" &&
      state.kind !== "not-available" &&
      state.kind !== "loaded"
    ) {
      assertNever(state, `unhandled page state on ${url}`);
    }
    if (state.kind === "load-error") {
      throw new Error(
        `${url} rendered an error state (HTTP ${status ?? "?"}): ${state.text.trim().slice(0, 200)}`,
      );
    }
    if (state.kind === "not-available") {
      const where = `${url} (HTTP ${status ?? "?"}) shows ${JSON.stringify(state.heading)}`;
      if (state.reason === "load-failed") {
        throw new Error(`${where} because the fetch FAILED: ${state.detail}`);
      }
      if (state.reason === "gated") {
        // `unreachable`, not `failed`: the page worked, the content is not
        // there. Deliberately NOT judged here — whether that is correct
        // depends on what this run released or finalized, and `visit()` is
        // generic and does not know. Recording the state distinctly is the
        // job; deciding what it means is Gene's.
        //
        // Careful about the scope of that: it is a statement about what
        // `visit()` can see, NOT a claim that a gated dashboard is fine. For
        // Risk in particular the RUN does know more — it exported, and export
        // is what sets `finalized_at` (Risk has no release concept; the client
        // gate is `clients.py`'s `reg.finalized_at is None`), so a gated risk
        // dashboard in THIS run would be suspicious. That pairing is surfaced
        // as a note at the `/dashboards/risk` visit in Phase 5, by the caller
        // that holds both facts, rather than by widening this function.
        throw new Unreachable(
          `${where} — content GATED, not released/finalized to this client: ${state.detail}`,
        );
      }
      throw new Indeterminate(
        `${where} but the copy matched neither the gated nor the load-failed wording — cannot say which: ${state.detail}`,
      );
    }

    // `textContent`, not `innerText`: a CSS-uppercased heading reads back
    // uppercased and would pin the styling instead of the copy.
    const h1 = page.locator("h1").first();
    // immediate-read: preceded by settled(), and the timeout argument waits
    // for the element to attach. Recorded as an observation; the landing
    // verdict comes from the HTTP status and the pathname, not from this text
    // alone.
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
 * The per-step `console.log` in `Recorder.step` is kept regardless: it needs no
 * hook to fire, so it is what survives the three unmeasured cases above.
 *
 * **Precise about what it writes, because the previous wording was not.** It
 * said the console line "writes as the run goes rather than at the end". Both
 * outcome lines are inside the completion branches, so as written it wrote for
 * every step that COMPLETED and nothing for the one that HUNG — narrower than
 * the sentence implied, sited exactly where someone reasoning about a timeout
 * would look. `Recorder.step` now also logs an `ENTERED` line on the way in,
 * and pushes the step onto `inFlight`, so a hanging step appears both in the
 * terminal and in the log's in-flight chain.
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

/**
 * REFUSE TO START IN THE WRONG AI MODE.
 *
 * Failed-item 2.2: a `docker compose down -v` or a deleted credential row
 * reverts the stack to fixture with no announcement, and the worst outcome
 * available is recording a whole take in fixture believing it is live. That
 * remedy used to be "a human checks the badge first". This is the gate.
 *
 * Symmetric on purpose -- see `helpers/aiModeGate.ts`. A rehearsal declares
 * `fixture` (the default) and refuses if the stack is live; a take declares
 * `live` and refuses if the stack is fixture.
 *
 * A SEPARATE CONTEXT, deliberately. `test.use` above puts video on the test's
 * own context, and this sign-in is scaffolding rather than demonstration --
 * routing it through the recorded page would put a throwaway login at the
 * front of the take. It costs one extra sign-in, which is the right price for
 * the one failure mode that cannot be repaired in post.
 */
test.beforeAll(async ({ browser }) => {
  // The hook needs its OWN timeout. `test.setTimeout(RUN_BUDGET_MS)` is called
  // inside the test body and does not cover a `beforeAll`, so this hook would
  // otherwise inherit the config's 90s -- and MEASURED 2026-09-10, a cold
  // sign-in plus a first compile of the `/api/proxy/admin/ai-status` route took
  // 78s on one attempt and 14s on the next. A gate that times out on a cold
  // stack fails the whole run before it starts, which makes the guard itself
  // the thing that breaks the take.
  test.setTimeout(5 * 60_000);

  const intended = intendedAiMode();
  const ctx = await browser.newContext();
  try {
    const probe = await ctx.newPage();
    await signIn(probe, ADMIN_EMAIL, ADMIN_PASSWORD);
    await assertAiMode(probe, intended);
  } finally {
    await ctx.close();
  }
});

test.afterEach(async () => {
  if (runState === null || runState.logged) return;
  runState.logged = true;
  // NOTHING TOUCHES THE VIDEO HERE. The save happens in `afterAll` below, and
  // the reason is measured rather than reasoned: `video.saveAs()` called from
  // `afterEach` NEVER RESOLVES.
  //
  // `saveAs` waits for the page to close, and Playwright closes the page AFTER
  // this hook returns -- so the hook waits for the page and the page waits for
  // the hook. Measured 2026-09-09 with a throwaway spec: the run died on
  // `Test timeout of 90000ms exceeded while running "afterEach" hook`, and the
  // video was not saved. The same spec's `afterAll` saved it in 2ms.
  //
  // That matters more than a tidier hook. A draft of this file did call
  // `saveAs` here, under a comment asserting it was "safe here even though the
  // file is not final until the context closes". That sentence was false, and
  // had it shipped, every rehearsal run would have hung in teardown and lost
  // BOTH the recording and the step log this hook exists to write.
  //
  // The trace is not copied here either, for a related reason: Playwright
  // writes `trace.zip` during fixture teardown, after this hook AND after
  // `afterAll`. Measured in the same probe -- the outputDir held no `.zip` at
  // either point. Stopping tracing by hand does produce the file, and it also
  // fails the test (`Must start tracing before stopping`), because it collides
  // with Playwright's own trace fixture. An instrument must not go red over
  // its own evidence handling, so the trace is copied out AFTER the runner
  // exits, by `e2e/scripts/run-engagement.sh`.
  const ctx = {
    legalName: runState.legalName,
    clientEmail: runState.clientEmail,
    clientId: runState.clientId,
    serviceIds: runState.serviceIds,
    // Deliberately null: the video does not exist yet at this point in the
    // lifecycle, and a log line naming a file that has not been written is the
    // success-record-before-the-success defect. `afterAll` writes the real
    // outcome to `recording.md` in the same folder.
    videoPath: null,
    outputDir: test.info().outputDir,
    completed: runState.completed,
  };
  try {
    writeLog(runState.rec, ctx);
  } catch (err) {
    // `logged` is set BEFORE the write, so a throw here would otherwise mean
    // no file and no retry — "I could not write" sharing a branch with
    // "already written", which is the shape this whole file is about. The flag
    // stays (a retry would just throw again on a full disk or a bad path);
    // what changes is that the record is not LOST. Dump it to stdout, which
    // needs no filesystem, and say plainly that the files are missing.
    //
    // eslint-disable-next-line no-console
    console.log(
      `\nfull-engagement: writeLog FAILED (${describe(err)}). No step-log.md or step-log.json was written. The complete record follows as JSON.\n`,
    );
    // eslint-disable-next-line no-console
    console.log(
      JSON.stringify(
        { ctx, steps: runState.rec.steps, notes: runState.rec.notes },
        null,
        2,
      ),
    );
  }
});

/**
 * Save the recording, and record whether the save worked.
 *
 * This runs AFTER the page and its context are torn down, which is the whole
 * point: `video.saveAs()` resolves only once the page has closed. In
 * `afterEach` it deadlocks (see the comment there); here it returned in 2ms in
 * the 2026-09-09 probe.
 *
 * `recording.md` is written from inside the branch that succeeded, never above
 * it, so the folder cannot claim a recording it does not contain. A failed
 * save writes the failure instead of writing nothing -- silence would be
 * indistinguishable from a run that never got this far.
 */
test.afterAll(async () => {
  if (runState === null) return;
  const dest = path.join(RUN_DIR, "engagement.webm");
  const lines: string[] = [`# Recording`, ``];
  try {
    fs.mkdirSync(RUN_DIR, { recursive: true });
    await runState.video?.saveAs(dest);
    if (fs.existsSync(dest)) {
      const bytes = fs.statSync(dest).size;
      lines.push(`- saved: engagement.webm`, `- bytes: ${bytes}`);
      // eslint-disable-next-line no-console
      console.log(`full-engagement: video saved (${bytes} bytes) -> ${dest}`);
    } else {
      lines.push(
        `- NOT SAVED: saveAs returned without error and no file exists at ${dest}.`,
        `- This run has no recording. Do not treat the step log as covering it.`,
      );
      // eslint-disable-next-line no-console
      console.log(`full-engagement: VIDEO MISSING after saveAs -> ${dest}`);
    }
  } catch (err) {
    lines.push(
      `- NOT SAVED: ${describe(err)}`,
      `- This run has no recording. Do not treat the step log as covering it.`,
    );
    // eslint-disable-next-line no-console
    console.log(`full-engagement: VIDEO SAVE FAILED -- ${describe(err)}`);
  }
  lines.push(
    ``,
    `The trace is NOT here yet. Playwright writes trace.zip during fixture`,
    `teardown, after this hook. \`e2e/scripts/run-engagement.sh\` copies it in`,
    `once the runner exits; if you launched the spec by hand, the trace is`,
    `under \`e2e/test-results/\` and the NEXT run will delete it.`,
    ``,
  );
  try {
    fs.writeFileSync(
      path.join(RUN_DIR, "recording.md"),
      lines.join("\n"),
      "utf8",
    );
  } catch {
    // The console lines above already carry the outcome; a missing recording.md
    // loses a convenience, not the fact.
  }
});

// ---------------------------------------------------------------------------
// The run
// ---------------------------------------------------------------------------

test("full engagement: intake -> five services -> release -> client view -> back to admin", async ({
  page,
}) => {
  test.setTimeout(RUN_BUDGET_MS);

  const rec = new Recorder();
  // Before the folder is created: a retry gets its own, so it cannot overwrite
  // the failed attempt's log.
  resolveRunDir(test.info().retry);
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
  /** Set by Phase 4's export step; read by Phase 5's risk-dashboard visit. */
  let riskExported: boolean | undefined;

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
      // Settle ONCE before the first read. The whole failure below was a
      // hydration race, and this is the cheap half of the fix: an unhydrated
      // checkbox reports its server-rendered value.
      const hydrated = await settled(page, 10_000);

      // Attempt EVERY service, then report. The first version threw inside the
      // loop, so one bad checkbox meant the three services after it were never
      // clicked at all — on the first real run that turned a single racy read
      // into three missing engagements, a missing deliverable, a missing Risk
      // Register, and eleven downstream rows. A step that gives up on the
      // first element of a list is a step that hides the rest of the list.
      const failures: string[] = [];
      for (const svc of SERVICES) {
        // click(), never check(): the wizard auto-saves on change, and
        // check()/uncheck() are recorded in CLAUDE.md as failing on exactly
        // that shape.
        const box = page.getByRole("checkbox", { name: svc.intakeLabel });
        try {
          await affordance(box, `intake checkbox ${svc.intakeLabel}`);
        } catch {
          failures.push(`${svc.intakeLabel}: checkbox never appeared`);
          continue;
        }
        const outcome = await driveCheckboxOn(box);
        if (outcome !== "checked") {
          failures.push(`${svc.intakeLabel}: ${outcome}`);
        }
      }

      if (failures.length > 0) {
        // `Indeterminate`, not `Unreachable`. The old message — "would not stay
        // checked after two clicks" — asserted a fact about the PRODUCT that
        // this run had not established: the box was read twice without waiting,
        // and on the first real run NIST CSF ended up genuinely selected (its
        // service was opened) while the log said it would not stay checked.
        // The failure was the reading, not the checkbox.
        throw new Indeterminate(
          `intake service selection could not be established${hydrated ? "" : " (the step never went quiet, so reads here are unreliable)"}: ${failures.join("; ")}`,
        );
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
      // #252. The legal name is the value the whole run is identified by —
      // "resolve the new tenant" matches on it, and every step after that
      // depends on the match. Advancing before the save lands is what stored
      // the email-domain fallback on runs 2 and 3.
      await waitForIntakeSave(page, rec, "the organization step");
    });

    await rec.step("intake", "fill the contact step", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      const full = page.locator("#display_name");
      await affordance(full, "contact full-name field");
      await full.fill(`Demo Client ${stamp}`);
      await page.locator("#title").fill("CISO");
      await waitForIntakeSave(page, rec, "the contact step");
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
        // #252 again. These targets gate the Submit button
        // (`targetsIncomplete` in Step6Review), so advancing before they save
        // is a second route to a disabled Submit with no cause established.
        if (targetsSet.length > 0) {
          await waitForIntakeSave(page, rec, "the per-service targets");
        }
      },
    );

    await rec.step("intake", "submit the intake", "ui", async () => {
      await page.getByRole("button", { name: "Next →" }).click();
      const submit = page.getByRole("button", {
        name: /^(Submit|Re-submit) intake$/,
      });
      await affordance(submit, "Submit intake button", CONTROL_WAIT_MS);

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
      // Branch on `settled`'s ANSWER. Discarding it is the defect this file
      // has a rule about: a false return means the page is still fetching, so
      // the re-read below describes nothing, and reporting `unreachable` off it
      // claims "I looked and it was not there" on the strength of a look that
      // did not happen.
      // immediate-read: settle-then-recheck. The first read is a fast path;
      // between the two the run establishes that the page went quiet, and
      // reports indeterminate when it could not. A disabled reading is never
      // turned into a cause.
      if (await submit.isDisabled()) {
        if (!(await settled(page, 10_000))) {
          throw new Indeterminate(
            "Submit intake read as disabled and the review step never went quiet — cannot separate a disabled button from an unhydrated one",
          );
        }
      }
      // immediate-read: settle-then-recheck. The first read is a fast path;
      // between the two the run establishes that the page went quiet, and
      // reports indeterminate when it could not. A disabled reading is never
      // turned into a cause.
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

    await rec.step("intake", "client signs out", "ui", () =>
      signOutViaNav(page),
    );

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
          // `/admin/queue/<id>` is an admin surface, so idiom 1 applies and
          // the "not available yet" idiom cannot occur here — but branch on
          // the state rather than assume, so a surprise reads as itself.
          const queueState = await pageState(page);
          if (queueState.kind === "load-error") {
            throw new Error(
              `the intake queue is showing an error, nothing can be published: ${queueState.text.trim().slice(0, 200)}`,
            );
          }
          if (queueState.kind === "not-available") {
            throw new Indeterminate(
              `the intake queue rendered a "not available yet" gate, which is not an idiom this admin surface was expected to use: ${queueState.detail}`,
            );
          }
          const queueH1 = await affordance(
            page.locator("h1").first(),
            "an <h1> on the intake queue",
            60_000,
          );
          // The comment here used to read "renders only when the queue loaded".
          // That is true of `IntakeQueue` and false of the page you may
          // actually be on: `/sign-in` and the admin shell's "Not authorized"
          // both render an `<h1>` too, and a bounce to either would have
          // satisfied the wait and let the loop below report zero unpublished
          // requests off a page that never showed any.
          const queueLanding = landingProblem(
            page,
            "/admin/queue",
            null,
            // immediate-read: affordance() already waited for this element to
            // be visible, so the text is present by the time it is read.
            await queueH1.textContent().catch(() => null),
          );
          if (queueLanding) {
            throw new Indeterminate(
              `not on the intake queue: ${queueLanding.message}`,
            );
          }

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
            // immediate-read: the settled() guard immediately above throws
            // indeterminate when the page never went quiet, so this count is
            // only taken off a page that finished rendering.
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
          // Same threading as `publishOk`: the message must not assert a fact
          // about a tenant nothing ever looked at. When `clientId` never
          // resolved, the whole publish block was skipped — no queue was
          // opened, no request was published, no engagement list was read — so
          // "no service was opened for this tenant" would be a claim with no
          // observation behind it.
          if (clientId === null) {
            throw new Indeterminate(
              `${svc.type}: the tenant was never resolved, so the publish block did not run and nothing looked at this service — its absence here is the run's, not the product's`,
            );
          }
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
            // `attached`, NOT `visible`, and this is the whole step.
            //
            // `Dropzone` renders `<input type="file" className="hidden">` --
            // Tailwind `hidden` is `display: none` -- because the visible
            // affordance is the drop target and the label wrapping it. So the
            // input is present, is what `setInputFiles` drives, and can never
            // become visible. Waiting for `visible` was a check that could not
            // pass, and it reported "affordance never appeared", which is a
            // sentence about the PRODUCT. Three runs recorded Tech Debt's
            // upload as an unreachable affordance on that basis, and the whole
            // service's finalize and release rows are downstream of it.
            //
            // Playwright drives hidden file inputs deliberately -- setInputFiles
            // does not require visibility -- so `attached` is the honest
            // precondition here and `visible` was never the right question.
            const file = page.locator('input[type="file"]').first();
            await affordance(
              file,
              "tech-debt inventory file input",
              CONTROL_WAIT_MS,
              "attached",
            );
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
          // The reload costs the workspace its whole mount chain again, and on
          // ATT&CK the Run AI control does not EXIST until that chain finishes.
          // Wait for the workflow to mount before looking for a button inside
          // it, so a slow mount is reported as a slow mount.
          await workspaceMounted(page, svc.slug);
          // CSF's control is labelled "Run AI (csf_score)"; ATT&CK and ZT use a
          // bare "Run AI". Matched by regex rather than by a per-service
          // literal so a copy change degrades to `unreachable` instead of a
          // silent miss.
          const runAi = page.getByRole("button", { name: /^Run AI\b/ }).first();
          await affordance(runAi, `${svc.slug} Run AI button`, CONTROL_WAIT_MS);
          // Settle before believing a disabled read: a visible-but-unhydrated
          // button reports disabled, and "React had not attached yet" must not
          // be logged as a product state. The cause is NOT asserted — the first
          // draft blamed "this assessment status" with nothing to support it.
          // immediate-read: settle-then-recheck. The first read is a fast
          // path; between the two the run establishes that the page went
          // quiet, and reports indeterminate when it could not. A disabled
          // reading is never turned into a cause.
          if (await runAi.isDisabled()) {
            if (!(await settled(page, 10_000))) {
              throw new Indeterminate(
                `${svc.slug}: Run AI read as disabled and the workspace never went quiet — cannot separate a disabled button from an unhydrated one`,
              );
            }
          }
          // immediate-read: settle-then-recheck. The first read is a fast
          // path; between the two the run establishes that the page went
          // quiet, and reports indeterminate when it could not. A disabled
          // reading is never turned into a cause.
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
          await affordance(
            approve,
            `${svc.slug} Approve control`,
            CONTROL_WAIT_MS,
          );

          // A visible button can still be pre-hydration. Give it a beat before
          // calling it disabled, so "React had not attached yet" is not
          // recorded as "the product disabled this control".
          // immediate-read: settle-then-recheck. The first read is a fast
          // path; between the two the run establishes that the page went
          // quiet, and reports indeterminate when it could not. A disabled
          // reading is never turned into a cause.
          if (await approve.isDisabled()) {
            if (!(await settled(page, 10_000))) {
              throw new Indeterminate(
                `${svc.slug}: Approve read as disabled and the workspace never went quiet — cannot separate a disabled button from an unhydrated one`,
              );
            }
          }
          // immediate-read: settle-then-recheck. The first read is a fast
          // path; between the two the run establishes that the page went
          // quiet, and reports indeterminate when it could not. A disabled
          // reading is never turned into a cause.
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
        // FOUR services, TWO vocabularies for one action. ATT&CK and Tech
        // Debt (the generic `DeliverableCard`) say "Finalize"/"Re-finalize";
        // CSF and ZT say "Send for evaluation"/"Re-run evaluation". This
        // locator carried only the first pair, so for CSF and ZT it named a
        // control the product does not have and the step could never have
        // concluded anything about them -- it was UNMEASURED, and it reported
        // as "affordance never appeared", which reads as a product failure.
        //
        // Derived, not recalled: the pairs are every match of
        //   git grep -nE '"(Finalize|Re-finalize|Send for evaluation|Re-run evaluation)"' -- apps/web/src
        // which returns exactly these four components and no others.
        //
        // The instrument accepts both because its job is to REACH the step.
        // That two surfaces name one action differently is a product finding,
        // and it is filed rather than fixed here -- this branch is e2e/ only.
        const finalize = page
          .getByRole("button", {
            name: /^(Finalize|Re-finalize|Send for evaluation|Re-run evaluation)$/,
          })
          .first();
        await affordance(
          finalize,
          `${svc.slug} Finalize button`,
          CONTROL_WAIT_MS,
        );
        // Same settle-then-recheck as Run AI and Approve. The cause is not
        // asserted: `canFinalize` gates on the assessment being approved OR
        // released, but a disabled read here may equally be a pre-hydration
        // one, and this run cannot tell the two apart from the button alone.
        // immediate-read: settle-then-recheck. The first read is a fast path;
        // between the two the run establishes that the page went quiet, and
        // reports indeterminate when it could not. A disabled reading is
        // never turned into a cause.
        if (await finalize.isDisabled()) {
          if (!(await settled(page, 10_000))) {
            throw new Indeterminate(
              `${svc.slug}: Finalize read as disabled and the workspace never went quiet — cannot separate a disabled button from an unhydrated one`,
            );
          }
        }
        // immediate-read: settle-then-recheck. The first read is a fast path;
        // between the two the run establishes that the page went quiet, and
        // reports indeterminate when it could not. A disabled reading is
        // never turned into a cause.
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
        await affordance(
          release,
          `${svc.slug} Release control`,
          CONTROL_WAIT_MS,
        );
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
          await affordance(
            gen,
            "Risk Register generate control",
            CONTROL_WAIT_MS,
          );
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

      // Captured so Phase 5 can pair it with what the CLIENT then sees. Risk
      // has no release concept — export is what sets `finalized_at`, which is
      // the field the client gate reads (`clients.py`: `reg.finalized_at is
      // None`). So a successful export here is the run's own evidence that a
      // gated risk dashboard later would be surprising.
      riskExported = await rec.step(
        "Risk-Register",
        "export XLSX / PDF / Word",
        "ui",
        async () => {
          const exportBtn = page.getByRole("button", {
            name: "Export XLSX / PDF / Word",
          });
          await affordance(
            exportBtn,
            "Risk Register export control",
            CONTROL_WAIT_MS,
          );
          const done = page.waitForResponse(
            (r) =>
              r.url().includes("/register/export") &&
              r.request().method() === "POST",
            { timeout: 300_000 },
          );
          await exportBtn.click();
          const res = await done;
          rec.note(`risk register export -> ${res.status()}`);
          return res.ok();
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

    await rec.step("client-view", "admin signs out", "ui", () =>
      signOutViaNav(page),
    );
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

    // ADJACENCY, not a verdict. `visit()` cannot know what this run released or
    // finalized, which is why it refuses to call a gated dashboard a failure —
    // but the RUN knows it exported, and export is what sets `finalized_at`,
    // the field the client gate reads. Pairing the two facts here gives the
    // reader what neither step had alone, without either step deciding.
    //
    // Same shape as threading `publishOk`: the step that knows tells the step
    // that does not.
    const riskVisit = rec.lastStep();
    if (
      riskExported === true &&
      riskVisit?.outcome === "unreachable" &&
      /GATED/.test(riskVisit.detail)
    ) {
      rec.note(
        "WORTH A LOOK: this run exported the Risk Register successfully (which is what sets finalized_at), " +
          "and the client's /dashboards/risk still reads as not-yet-finalized. Those two should not both be true. " +
          "Stated as an adjacency for a human to judge, not as a verdict — see the export row and the visit row above.",
      );
    }

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
        const resultsState = await pageState(page);
        if (resultsState.kind === "load-error") {
          throw new Error(
            `/results is showing an error, so any link count is meaningless: ${resultsState.text.trim().slice(0, 200)}`,
          );
        }
        if (resultsState.kind === "not-available") {
          // A gated /results is a real observation about what this client can
          // see, and counting links under it would report zero as if the page
          // had listed nothing.
          throw new Unreachable(
            `/results shows ${JSON.stringify(resultsState.heading)} (${resultsState.reason}), so there is no link list to count: ${resultsState.detail}`,
          );
        }
        const links = page.getByRole("link", {
          name: /PDF|XLSX|Word|Download/i,
        });
        // immediate-read: the settled() guard immediately above throws
        // indeterminate when the page never went quiet, so this count is only
        // taken off a page that finished rendering.
        const n = await links.count();
        rec.note(`client /results exposes ${n} download link(s)`);
      },
    );

    // === Phase 6: back to admin, and walk the workspace ====================

    await rec.step("admin-walk", "client signs out", "ui", () =>
      signOutViaNav(page),
    );
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
    // The in-flight chain, named FIRST. A step abandoned mid-await pushes no
    // row of its own, so without this the step that consumed the budget is the
    // one step absent from the table — precisely the thing you opened the file
    // to find.
    if (rec.inFlight.length > 0) {
      lines.push("**IN FLIGHT WHEN THE RUN STOPPED** (outermost first):");
      lines.push("");
      for (const f of rec.inFlight) {
        lines.push(
          `- \`[${f.phase}] ${f.name}\` (${f.via}) — running for ${Date.now() - f.started}ms, no row of its own below`,
        );
      }
      lines.push("");
      lines.push(
        "This is the likeliest place the budget went. It has no row in the Steps",
      );
      lines.push(
        "table because a step abandoned mid-await never reaches its own record.",
      );
      lines.push("");
    } else {
      lines.push(
        "No step was in flight, so the run stopped between steps rather than inside one.",
      );
      lines.push("");
    }
  }
  lines.push(
    "This run asserts nothing about content. Every line below is an OBSERVATION.",
  );
  lines.push(
    "A `failed` or `unreachable` row is a finding to look at, not a broken test.",
  );
  lines.push("");
  // ==========================================================================
  // THE HEADLINE MUST NOT BE SPLITTABLE INTO SOMETHING FLATTERING.
  //
  // The requirement is stronger than "be accurate". It is that an accurate
  // quotation of PART of this block must not be misleading. "38 ok" is true
  // and, on its own, false in effect — it was true of a run in which three
  // services, the entire deliverable path and the Risk Register were never
  // exercised at all.
  //
  // So the smallest quotable unit carries both halves. There is no bare `ok`
  // count on a line of its own anywhere above the breakdown, and the verdict
  // sentence names reached AND not-reached together or it does not render.
  // The per-outcome numbers still appear, but BELOW the verdict and under a
  // heading that travels with them if excerpted.
  //
  // Same failure this file records everywhere else: the thing keeping a number
  // honest must live in the artifact carrying the number, not beside it.
  // ==========================================================================
  // DERIVED from a total classification, not from two hand-written sums.
  //
  // It was `ok + failed` and `missed + unknown`. Those happen to be correct,
  // but nothing enforced that the two sums partition the outcomes: a fifth
  // outcome would have been silently absent from BOTH, and the verdict would
  // have quietly described fewer steps than the run recorded.
  //
  // `Record<Outcome, ...>` makes the classification exhaustive — adding an
  // outcome without deciding which side it falls on is a compile error, not a
  // reporting gap. Which side matters: `indeterminate` means "I could not
  // look", so it belongs with NOTHING. Putting it on the reached side would
  // make the verdict flattering in exactly the category the fourth outcome
  // exists to protect — and run 1, which had zero indeterminate steps, could
  // not have exposed that.
  const CONCLUSION: Record<Outcome, "reached" | "nothing"> = {
    ok: "reached",
    failed: "reached",
    unreachable: "nothing",
    indeterminate: "nothing",
  };
  const measured = rec.steps.filter(
    (s) => CONCLUSION[s.outcome] === "reached",
  ).length;
  const notMeasured = rec.steps.filter(
    (s) => CONCLUSION[s.outcome] === "nothing",
  ).length;
  const clean = failed === 0 && notMeasured === 0;

  lines.push("## Verdict");
  lines.push("");
  if (clean) {
    lines.push(
      `**CLEAN — all ${rec.steps.length} steps reached a conclusion and none failed.**`,
    );
  } else {
    // One sentence, both numbers, no separable flattering half.
    lines.push(
      `**NOT CLEAN — ${measured} of ${rec.steps.length} steps reached a conclusion ` +
        `(${failed} of them a FAILURE); ${notMeasured} steps concluded NOTHING.**`,
    );
  }
  lines.push("");
  lines.push(
    "A step MEASURED the product only if it reached a conclusion — `ok` or `failed`.",
  );
  lines.push(
    "`unreachable` and `indeterminate` are not passes and not failures: they are",
  );
  lines.push(
    "work this run did not get to do, so they mark what it says NOTHING about.",
  );
  if (notMeasured > 0) {
    lines.push("");
    lines.push(
      `> Quoting any single figure below without the ${notMeasured} not-reached alongside it`,
    );
    lines.push(
      "> overstates what this run covered. Quote the verdict line, not a tally.",
    );
  }
  lines.push("");
  lines.push("### Breakdown");
  lines.push("");
  lines.push(`- steps recorded: ${rec.steps.length}`);
  lines.push(
    `- reached a conclusion: ${measured} — of which ok ${ok}, failed ${failed}`,
  );
  lines.push(
    `- concluded nothing: ${notMeasured} — of which unreachable ${missed}, indeterminate ${unknown}`,
  );
  lines.push("");

  // ==========================================================================
  // WORKAROUNDS, stated where a reader of a CLEAN run will see them.
  //
  // The whole point: a clean run that depended on a workaround for an open
  // defect must not read as a clean run that did not. Buried in `## Notes`
  // among sixty lines, this would be invisible; here it sits directly under
  // the verdict it qualifies.
  //
  // And it reports whether each workaround DID WORK, so the day the underlying
  // defect is fixed the log starts saying "not needed" on its own rather than
  // waiting for someone to think to check.
  // ==========================================================================
  if (rec.workarounds.length > 0) {
    const refs = [...new Set(rec.workarounds.map((w) => w.ref))].sort();
    const neededRefs = [
      ...new Set(rec.workarounds.filter((w) => w.needed).map((w) => w.ref)),
    ].sort();
    lines.push("### Workarounds in force");
    lines.push("");
    lines.push(
      `This run applied workarounds for open defects: ${refs.join(", ")}.`,
    );
    lines.push("");
    if (neededRefs.length > 0) {
      lines.push(
        `**${neededRefs.join(", ")} DID work this run — the defect is still live.** Any`,
      );
      lines.push(
        "conclusion below holds only because of it, and would not hold without it.",
      );
    } else {
      lines.push(
        "**None of them did any work this run.** That is evidence the underlying",
      );
      lines.push(
        "defects may be fixed — worth checking whether these waits can be removed,",
      );
      lines.push("rather than carrying them forward forever.");
    }
    lines.push("");
    for (const w of rec.workarounds) {
      lines.push(
        `- ${w.ref} — ${w.needed ? "**needed**" : "not needed"}: ${w.detail}`,
      );
    }
    lines.push("");
  }
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
  lines.push(
    `- video: see recording.md in this folder (written after the run's page closes)`,
  );
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
  if (!ctx.completed) {
    // Notes and steps are separate arrays, and a note written partway through a
    // step SURVIVES that step being abandoned. So on a partial run a note can
    // describe work whose step has no row — e.g. "run-ai -> 200" with no Run AI
    // row, because the note fired and the reload after it hung. That is not a
    // contradiction in the product; it is this file's two records having
    // different granularity, and saying so here is cheaper than someone
    // deducing it.
    lines.push(
      "> On a PARTIAL run a note may describe work whose step has no row above:",
    );
    lines.push(
      "> notes are written as a step proceeds, and an abandoned step never records",
    );
    lines.push(
      "> its own outcome. Cross-check against the in-flight chain at the top.",
    );
    lines.push("");
  }
  for (const n of rec.notes) lines.push(`- ${n.replace(/\|/g, "\\|")}`);
  lines.push("");

  fs.mkdirSync(RUN_DIR, { recursive: true });
  fs.writeFileSync(path.join(RUN_DIR, "step-log.md"), lines.join("\n"), "utf8");
  fs.writeFileSync(
    path.join(RUN_DIR, "step-log.json"),
    JSON.stringify(
      {
        stamp: RUN_STAMP,
        // FIRST key, and deliberately a compound string: whatever a script or
        // a person grabs first from this file should be the figure that
        // degrades SAFELY, not the flattering one. `summary.ok` alone is the
        // number that misleads, so it is nested a level down behind a verdict
        // that cannot be read as clean when it is not.
        headline: clean
          ? `CLEAN — all ${rec.steps.length} steps reached a conclusion and none failed`
          : `NOT CLEAN — ${measured}/${rec.steps.length} steps reached a conclusion (${failed} failed); ${notMeasured} concluded nothing`,
        clean,
        summary: {
          total: rec.steps.length,
          // `reachedAConclusion` and `concludedNothing` are the pair that must
          // travel together; the four raw counts sit under them.
          reachedAConclusion: measured,
          concludedNothing: notMeasured,
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
        // Open defects this run worked around, and whether each did work. A
        // consumer treating a clean run as clean must be able to see what the
        // cleanliness depended on.
        workarounds: rec.workarounds,
        stepOrder: "completion",
        // Steps entered but never completed — they have no entry in `steps`.
        inFlightAtStop: rec.inFlight.map((f) => ({
          phase: f.phase,
          name: f.name,
          via: f.via,
          runningMs: Date.now() - f.started,
        })),
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
    // Terminal line, same rule: this is the most-quoted single line the run
    // produces, so it leads with the verdict rather than with the ok count.
    `\nfull-engagement: ${
      clean
        ? `CLEAN — all ${rec.steps.length} steps reached a conclusion`
        : `NOT CLEAN — ${measured}/${rec.steps.length} reached a conclusion (${failed} failed); ${notMeasured} concluded nothing`
    }\n  (ok ${ok}, failed ${failed}, unreachable ${missed}, indeterminate ${unknown})\n  ${RUN_DIR}\n`,
  );
}
