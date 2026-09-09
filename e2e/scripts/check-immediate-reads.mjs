#!/usr/bin/env node
/**
 * Flag Playwright IMMEDIATE GETTERS used where a wait is needed.
 *
 * ## Why this is a script and not a paragraph
 *
 * `e2e/engagement/full-engagement.spec.ts` carried a rule in its header saying
 * "never a bare `isVisible()`/`count()`". That named two methods. The first
 * real run of that spec broke on `isChecked()` — outside the list, never swept
 * — which read a checkbox mid-re-render, clicked it a second time, toggled it
 * off, and recorded "would not stay checked" about a box that had in fact been
 * selected. One racy read cascaded into three services never opened and eleven
 * downstream rows.
 *
 * A rule that lives only in prose gets followed on the line you are thinking
 * about and skipped on the line next to it. So this fires instead.
 *
 * ## The set is Playwright's, not ours
 *
 * Playwright splits its own API in two, and the split is the whole rule:
 *
 *   - Auto-waiting ASSERTIONS poll until they pass or time out
 *     (`expect(locator).toBeChecked()` and friends).
 *   - IMMEDIATE GETTERS read one instant and never wait.
 *
 * The getters are enumerated below because Playwright enumerates them, not
 * because someone listed the ones they could think of. `is*` is matched by
 * PATTERN rather than by name, so a getter added upstream is caught without an
 * edit here.
 *
 * ## Report-only, deliberately
 *
 * Findings never fail the run (see #235's posture). A blocking gate whose
 * cheapest route to green is deleting the offending check steers the author
 * into the very defect it exists to catch — the same finding this repo already
 * recorded for `check_plan_totals.py`.
 *
 * Exit codes, which are NOT the same thing as findings:
 *
 *   0 — ran, looked, and reported whatever it found (findings included).
 *   2 — COULD NOT LOOK: the target path does not exist or held no `.ts` files.
 *
 * The 2 matters more than it looks. `check_test_integrity.py` shipped with
 * `rglob` on a missing path returning nothing and printing "clean", so its
 * correctness lived in a `working-directory:` line in another file. A checker
 * whose "nothing to complain about" branch and whose "I could not look" branch
 * are the same branch is the defect, not the guard against it.
 *
 * ## Waiving a hit
 *
 * Not every immediate read is wrong. A "is an error on screen right now" probe
 * is correct precisely because it does not wait, and a poll loop must read
 * immediately by construction. Mark those:
 *
 *     // immediate-read: <why waiting would be wrong here>
 *
 * on the line itself or on any line of the comment block directly above it.
 * An empty reason is not a reason and is reported as if unwaived — the same
 * convention, and the same rule, as `# test-integrity: <reason>`.
 *
 * ## RUN THIS AFTER PRETTIER, NEVER BEFORE
 *
 * Waiver association is adjacency, so it is not stable under reformatting —
 * the same property `check_recalled_counts.py` has, and for the same reason.
 * Observed on this gate's first use: prettier wrapped an expression and put a
 * bare `(` between a waiver and the read it covered, which detached it. The
 * finding was real, the fix was to restructure the expression, and the point
 * is that a clean result taken BEFORE the formatter says nothing about the
 * tree after it.
 *
 * Usage:  node e2e/scripts/check-immediate-reads.mjs [path ...]
 *         (defaults to the directory this script lives in, one level up)
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/**
 * Scoped to `e2e/engagement`, deliberately, and NOT to all of `e2e/`.
 *
 * Pointed at the whole suite this reports 50 unwaived hits in the other specs
 * <!-- counted: node e2e/scripts/check-immediate-reads.mjs e2e, 2026-09-09 -->
 * on day one. A gate nobody reads is worse than no gate, because it looks like
 * coverage while suppressing nothing — so a finding list that arrives already
 * drowned trains its own readers to skip it.
 *
 * Scoped, it reads 0 unwaived and every future hit is a real one.
 *
 * **The other 50 are UNTRIAGED, not benign.** Nobody has checked whether any of
 * them decides a recorded outcome, which is the only question that makes an
 * immediate read a defect. Filed as #253 rather than left here as noise —
 * visible and counted beats suppressed. Widen this default when #253 closes,
 * not before.
 *
 * Pass a path to override:  node e2e/scripts/check-immediate-reads.mjs e2e
 */
const DEFAULT_ROOT = path.resolve(HERE, "..", "engagement");

/**
 * Immediate getters. `is[A-Z]\w*` covers isChecked, isDisabled, isEditable,
 * isEnabled, isHidden and isVisible by shape, so an upstream addition is
 * caught. The rest are named because they share no prefix.
 */
const IMMEDIATE = new RegExp(
  String.raw`\.(is[A-Z]\w*|count|textContent|innerText|inputValue|getAttribute|allTextContents|allInnerTexts)\s*\(`,
  "g",
);

const WAIVER = /immediate-read:\s*(\S.*)$/;

/**
 * Collect every `.ts` file under `root`, skipping node_modules.
 *
 * `.ts` ONLY, and that is a fix rather than an oversight. The pattern below
 * matches a method NAME and cannot see its receiver, so `.isDirectory()` on a
 * Node `Dirent` reads exactly like `.isVisible()` on a Locator — this gate
 * reported two such hits in its own source on its first cross-directory run.
 * Playwright test code is `.ts` here, so scoping the scan to it removes that
 * whole class of false positive without weakening the pattern.
 *
 * The residual is stated rather than assumed: a `.ts` file calling
 * `.isDirectory()` or any same-named method on a non-Locator would still be
 * reported. That is what the waiver comment is for, and a false positive
 * carrying a written reason is cheaper than a pattern narrowed until it misses.
 */
function collect(root) {
  const out = [];
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (e.name === "node_modules" || e.name.startsWith(".")) continue;
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (/\.ts$/.test(e.name) && !e.name.endsWith(".d.ts")) {
        out.push(full);
      }
    }
  };
  const stat = fs.statSync(root, { throwIfNoEntry: false });
  if (stat === undefined) return null; // could not look
  if (stat.isDirectory()) walk(root);
  else out.push(root);
  return out;
}

/**
 * Is this line inside a block comment or a line comment?
 *
 * Prose ABOUT these getters is not a use of them, and this file's own subject
 * means the specs discuss them constantly. Tracking `/* ... *\/` across lines
 * rather than testing each line in isolation, because a doc comment naming
 * `isChecked()` would otherwise be reported forever.
 */
function commentMask(lines) {
  const mask = [];
  let inBlock = false;
  for (const line of lines) {
    const trimmed = line.trim();
    const startsInBlock = inBlock;
    const opens = (line.match(/\/\*/g) ?? []).length;
    const closes = (line.match(/\*\//g) ?? []).length;
    if (opens > closes) inBlock = true;
    else if (closes > opens) inBlock = false;
    mask.push(
      startsInBlock || trimmed.startsWith("*") || trimmed.startsWith("//"),
    );
  }
  return mask;
}

/** A waiver on the line itself, or anywhere in the comment block above it. */
function waivedAt(lines, idx) {
  const own = WAIVER.exec(lines[idx]);
  if (own) return own[1].trim();
  for (let i = idx - 1; i >= 0; i -= 1) {
    const t = lines[i].trim();
    if (t === "") continue;
    if (!(t.startsWith("//") || t.startsWith("*") || t.startsWith("/*"))) break;
    const m = WAIVER.exec(lines[i]);
    if (m) return m[1].trim();
  }
  return null;
}

function main() {
  const roots = process.argv.slice(2);
  const targets = roots.length > 0 ? roots : [DEFAULT_ROOT];

  const files = [];
  for (const r of targets) {
    const found = collect(path.resolve(r));
    if (found === null) {
      console.error(`immediate-reads: cannot look — path does not exist: ${r}`);
      return 2;
    }
    files.push(...found);
  }
  if (files.length === 0) {
    console.error(
      `immediate-reads: cannot look — no .ts files under: ${targets.join(", ")}`,
    );
    return 2;
  }

  const findings = [];
  let waived = 0;
  for (const file of files) {
    const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
    const isComment = commentMask(lines);
    lines.forEach((line, i) => {
      if (isComment[i]) return;
      IMMEDIATE.lastIndex = 0;
      let m;
      while ((m = IMMEDIATE.exec(line)) !== null) {
        if (waivedAt(lines, i)) {
          waived += 1;
          continue;
        }
        findings.push({
          file: path.relative(process.cwd(), file),
          line: i + 1,
          call: m[1],
          text: line.trim().slice(0, 120),
        });
      }
    });
  }

  console.log(
    `immediate-reads: scanned ${files.length} file(s); ${findings.length} unwaived, ${waived} waived`,
  );
  if (findings.length > 0) {
    console.log(
      "\nEach of these reads ONE INSTANT and never waits. That is a defect wherever\n" +
        "the result decides a recorded outcome. Wait first (an auto-waiting\n" +
        "assertion, an explicit waitFor, or a poll), or mark it:\n" +
        "    // immediate-read: <why waiting would be wrong here>\n",
    );
    for (const f of findings) {
      console.log(`  ${f.file}:${f.line}  .${f.call}()  ${f.text}`);
    }
    console.log(
      "\nREPORT-ONLY: this never fails the run. Findings are for a human to\n" +
        "classify — a blocking gate here would make deleting the check the\n" +
        "cheapest route to green.",
    );
  }
  return 0;
}

process.exit(main());
