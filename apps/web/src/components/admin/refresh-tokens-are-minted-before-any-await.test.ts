import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * A refresh token is minted BEFORE any `await` in its function (#292).
 *
 * ## Why this is a test and not a comment
 *
 * `useRefreshFailures.begin` documents the rule at the definition. That is
 * where the next person will read it, and it is still only prose: nothing
 * stops a late mint, and the round that WROTE the rule left four call sites
 * violating it.
 *
 * `CLAUDE.md`: the reflex survives the rule until the rule has a gate. This
 * file is the gate.
 *
 * ## The defect it catches
 *
 * A token's ordering is the order `begin` was CALLED. Mint it after an await
 * and the tokens are ordered by when those awaits RESOLVED instead — so a
 * refresh invoked FIRST whose earlier fetch is slow mints the LATER token,
 * owns the slot, and writes over the newer one. That is verbatim the defect
 * the token replaced, and it was introduced by the fix for it.
 *
 * Three of the four sites were masked by an `if (seq !== assessmentSeq.current)`
 * early-return belonging to an unrelated mechanism. A guard that survives by
 * accident loses its protection the moment someone moves that check, which is
 * why "it happens to be safe today" was not good enough.
 *
 * ## Stated limit
 *
 * The scan is brace-balanced from each `async` opener and does not model
 * nested function declarations: a `beginRefresh` inside a callback defined
 * after an await would be reported. That direction is a FALSE POSITIVE, which
 * is loud and fixable at review.
 *
 * **IT CAN PRODUCE A FALSE CLEAN, and this paragraph used to deny it.** It
 * read "It cannot produce a false clean, which is the direction that matters"
 * -- a scope claim wider than its own argument, stated exactly where someone
 * would check, which is the shape `CLAUDE.md` calls worse than no comment.
 *
 * ## The opener now covers declarations (#385)
 *
 * It used to match async ARROW FUNCTIONS ONLY, so an `async function`
 * DECLARATION was invisible to it -- and the admin tree is full of those
 * (`grep -rn "async function" src/components/admin`). This paragraph stated
 * that limit correctly and then said widening "is deliberately not made
 * here", deferring it to the PR that adds the next tokens.
 *
 * #385 IS THAT PR. `onChangeTargetStage` and its CSF twin now mint a token
 * and catch, inside async function declarations -- exactly the shape the old
 * opener could not see, so the gate would have gone on reporting clean over
 * the code written to satisfy it. The deferral is discharged rather than
 * restated: a deferral its own fix has already met reads as a live limit, and
 * sends the next reader to build what ships.
 *
 * `asyncBodyStarts` below finds both forms. The declaration form is scanned
 * with BALANCED PARENS rather than a negated character class, because a
 * parameter list can contain parentheses of its own --
 * `SecurityClassificationQueue.run` takes `fn: () => Promise<CapabilityList>`,
 * and a class-based match stops at the first `)`, fails to find a body, and
 * reports that function CLEAN without having looked at it. The return-type
 * annotation is then skipped at angle-bracket depth, so a `{` inside
 * `Promise<{ ... }>` is not mistaken for the body.
 *
 * The patterns are deliberately NOT quoted in this prose: writing a regex
 * into a comment is how this file acquired an invisible BACKSPACE byte while
 * an earlier version of this paragraph was being written, which is the defect
 * `check_no_control_chars.py` exists for. Read them at the definitions.
 *
 * ## What is still invisible
 *
 * METHOD SHORTHAND -- an `async` name directly followed by a parameter list,
 * in an object literal or a class body. `arrowBodyStart` reads the name, then
 * requires `=>`, finds a `{` instead and returns -1, so the body is not
 * scanned. No admin component uses it today; the check is the grep for an
 * `async` line whose next token is a name and then an open paren, and it
 * comes back empty. The day one appears, its late mints go unreported.
 *
 * THIS LIST IS A FLOOR, NOT A CENSUS, and it says so because the previous
 * version closed with "the list above is what is left" -- a completeness
 * claim, in the paragraph a reader checks INSTEAD of reading the pattern,
 * and it was false. An adversarial pass named four more, all latent in this
 * tree and none of them on the list:
 *
 *   - a GENERIC async arrow. `arrowBodyStart` wants `(` or an identifier
 *     after `async`, so `async <T,>(x: T) => {}` yields no body.
 *   - a declaration whose TYPE PARAMETERS contain a brace:
 *     `async function f<T extends { a: 1 }>(...)` hits that `{` while
 *     scanning for `(` and returns -1.
 *   - `codeOnly` does not model REGEX LITERALS, so a quote or backtick
 *     inside one opens a phantom string and blanks live code to spaces.
 *   - `unscannable` detects only UNDER-closure. A body terminated EARLY by a
 *     stray `}` -- which is exactly what that phantom string produces --
 *     balances at the wrong place and is reported scannable, after which
 *     `lateMints` reads a truncated body and reports it clean.
 *
 * Tracked rather than fixed here; adding them is a change to what this gate
 * reports across four workspaces, and this PR is already carrying a reverted
 * and rebuilt fix.
 *
 * An unbalanced brace walk is no longer silent, within that bound:
 * `unscannable` collects those bodies and the suite asserts it is empty, so
 * "I could not look" and "nothing to complain about" stop sharing a branch.
 */

const ADMIN = join(process.cwd(), "src/components/admin");

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry))
      out.push(full);
  }
  return out;
}

/**
 * A same-length copy with comment and string CONTENTS blanked to spaces.
 *
 * Offsets and line numbers are preserved; only the characters are removed.
 * Blanking rather than deleting is the point: these files are full of braces
 * inside comments and string literals, and a brace-balance walk over raw
 * source mis-counts and swallows the rest of the file.
 *
 * Not hypothetical. The first version of this detector skipped it and reported
 * ALL SIX mints as late -- including the ones sitting on the first line of
 * their own function. A detector that flags everything is as useless as one
 * that flags nothing, and only running it showed that.
 */
function codeOnly(src: string): string {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (c === "/" && next === "/") {
      const end = src.indexOf("\n", i);
      const stop = end === -1 ? src.length : end;
      out += " ".repeat(stop - i);
      i = stop;
      continue;
    }
    if (c === "/" && next === "*") {
      const end = src.indexOf("*/", i + 2);
      const stop = end === -1 ? src.length : end + 2;
      out += src.slice(i, stop).replace(/[^\n]/g, " ");
      i = stop;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      out += c;
      i++;
      while (i < src.length) {
        if (src[i] === "\\") {
          out += "  ";
          i += 2;
          continue;
        }
        if (src[i] === quote) {
          out += quote;
          i++;
          break;
        }
        out += src[i] === "\n" ? "\n" : " ";
        i++;
      }
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

/**
 * The body start of an async function DECLARATION whose keyword ends at
 * `from`, or -1 when this is not one.
 *
 * The returned offset is just PAST the `{`, matching what the arrow form
 * yields, so both feed the same brace walk.
 *
 * Both scans below are balanced rather than pattern-matched, and each closes
 * a FALSE-CLEAN direction:
 *
 *   - PARENS. A parameter list can hold parentheses: `fn: () => Promise<T>`.
 *     Stopping at the first `)` leaves the scan hunting a body it cannot
 *     find, and a function that is never scanned is a function reported
 *     clean.
 *   - ANGLE BRACKETS. A return type can hold braces: `Promise<{ n: number }>`.
 *     Taking the first `{` after the parameters would start the "body" inside
 *     the type, and the brace walk would then end early -- clean again, from
 *     a body nothing read.
 *
 * A `;` before the body means an overload signature or a non-function, and
 * yields -1 rather than scanning on into whatever follows.
 */
function declarationBodyStart(src: string, from: number): number {
  let i = from;
  while (i < src.length && src[i] !== "(") {
    if (src[i] === "{" || src[i] === ";") return -1;
    i++;
  }
  let depth = 0;
  for (; i < src.length; i++) {
    if (src[i] === "(") depth++;
    else if (src[i] === ")" && --depth === 0) {
      i++;
      break;
    }
  }
  if (depth !== 0) return -1;
  let angle = 0;
  for (; i < src.length; i++) {
    const c = src[i];
    if (c === "<") angle++;
    else if (c === ">") {
      if (angle > 0) angle--;
    } else if (c === ";") return -1;
    else if (c === "{" && angle === 0) return i + 1;
  }
  return -1;
}

/**
 * The body start of an async ARROW whose `async` keyword ends at `from`, or
 * -1 when this is not one.
 *
 * BOTH parameter forms are balanced, and the parenthesised one is why this
 * exists. The opener used to spell it `\([^)]*\)`, which cannot cross a `)`
 * -- so `async (cb: () => void) => { await g(); beginRefresh("x"); }` matched
 * NO opener at all, was never scanned, and came back clean. That is the same
 * false-CLEAN direction `declarationBodyStart` was written to close, left
 * open in the sibling branch, under a "what is still invisible" paragraph
 * that named only method shorthand. Found by adversarial review; latent
 * rather than live, which is exactly why nothing would have surfaced it.
 */
function arrowBodyStart(src: string, from: number): number {
  let i = from;
  while (i < src.length && /\s/.test(src[i])) i++;
  if (src[i] === "(") {
    let depth = 0;
    for (; i < src.length; i++) {
      if (src[i] === "(") depth++;
      else if (src[i] === ")" && --depth === 0) {
        i++;
        break;
      }
    }
    if (depth !== 0) return -1;
  } else if (/[A-Za-z_$]/.test(src[i] ?? "")) {
    while (i < src.length && /[\w$]/.test(src[i])) i++;
  } else {
    return -1;
  }
  // A return-type annotation may sit between the parameters and the arrow,
  // and may itself contain braces (`): Promise<{ n: number }> =>`), so the
  // scan to `=>` runs at angle depth exactly as the declaration form does.
  let angle = 0;
  for (; i < src.length; i++) {
    const c = src[i];
    if (c === "<") angle++;
    else if (c === ">") {
      // `=>` is the terminator, not a closing angle bracket.
      if (src[i - 1] === "=" && angle === 0) {
        i++;
        break;
      }
      if (angle > 0) angle--;
    } else if (c === ";") return -1;
  }
  while (i < src.length && /\s/.test(src[i])) i++;
  return src[i] === "{" ? i + 1 : -1;
}

/**
 * Offsets just past the `{` opening each async function body in `src`.
 *
 * The opener now matches only the `async` KEYWORD; each form's parameters,
 * return type and body brace are found by a balanced scan, because every
 * character class tried here has had a false-clean hiding in it.
 */
function asyncBodyStarts(src: string): number[] {
  const out: number[] = [];
  const opener = /\basync\b/g;
  let m: RegExpExecArray | null;
  while ((m = opener.exec(src)) !== null) {
    const after = m.index + m[0].length;
    const decl = /^\s+function\b/.exec(src.slice(after, after + 32));
    const body =
      decl !== null
        ? declarationBodyStart(src, after + decl[0].length)
        : arrowBodyStart(src, after);
    if (body !== -1) out.push(body);
  }
  return out;
}

/**
 * Offsets of async bodies this scan could NOT read, because the brace walk
 * never balanced.
 *
 * Separate from `lateMints` on purpose: a body nobody scanned is not a body
 * with nothing wrong in it, and this repo's rule is that those two must never
 * be the same branch.
 */
export function unscannable(raw: string): number[] {
  const src = codeOnly(raw);
  const out: number[] = [];
  for (const start of asyncBodyStarts(src)) {
    let depth = 1;
    let i = start;
    for (; i < src.length && depth > 0; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}") depth--;
    }
    if (depth !== 0) out.push(start);
  }
  return out;
}

/** Offsets of every `beginRefresh(` that follows an `await` in its own async body. */
export function lateMints(raw: string): number[] {
  const src = codeOnly(raw);
  const bad: number[] = [];
  const unbalanced: number[] = [];
  for (const start of asyncBodyStarts(src)) {
    let depth = 1;
    let i = start;
    for (; i < src.length && depth > 0; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}") depth--;
    }
    // AN UNBALANCED WALK IS "I COULD NOT LOOK", AND IT USED TO SHARE THIS
    // BRANCH WITH "NOTHING TO COMPLAIN ABOUT". The comment here claimed the
    // emptiness guard would report it; that guard counts `beginRefresh(` over
    // RAW text and asserts a floor, so a body skipped for imbalance leaves
    // its count untouched and cannot fire. Collected and asserted separately
    // instead -- see `unscannable` below.
    if (depth !== 0) {
      unbalanced.push(start);
      continue;
    }
    const body = src.slice(start, i - 1);
    const firstAwait = body.search(/\bawait\b/);
    if (firstAwait === -1) continue;
    const mintRe = /\bbeginRefresh\s*\(/g;
    let g: RegExpExecArray | null;
    while ((g = mintRe.exec(body)) !== null) {
      if (g.index > firstAwait) bad.push(start + g.index);
    }
  }
  // Not merged into `bad`: an unreadable body is a different claim from a
  // late mint, and `unscannable` is what the suite asserts on.
  void unbalanced;
  return bad;
}

describe("refresh tokens are minted before any await", () => {
  it("finds the admin components at all", () => {
    expect(walk(ADMIN).length).toBeGreaterThanOrEqual(15);
  });

  it("finds the mints it is scanning for", () => {
    // THE SELECTOR MUST SELECT SOMETHING.
    //
    // Everything below reports offenders. If every `beginRefresh` moved out of
    // this directory -- renamed, relocated, or the hook replaced -- the file
    // count above still passes, the offender list is still empty, and this
    // gate goes green over ZERO mints. A selector that selects nothing passes,
    // and it passes with the answer you were hoping for.
    //
    // THE COUNT THAT STOOD HERE IS DELETED RATHER THAN UPDATED. It read "Six
    // exist today" above a list of NINE, and named `score-gap` twice -- a key
    // #185 removed when it split that refresh into `score` and `gap`. Wrong
    // when written and wronger afterwards, in the file whose job is to
    // enumerate them.
    //
    // `CLAUDE.md`'s first rule for numbers applies exactly: if a number
    // describes a list in the same document, delete the number and let the
    // list be the count. The source names in use, which a reader can verify
    // with `grep -rhoE 'beginRefresh\("[^"]+"\)' src/components/admin`:
    //
    //     deliverable   Csf, Zt, Attack, TechDebt
    //     score, gap    Csf, Zt
    //     interview     Csf
    //     heatmap       Attack
    //     overlap-plan  TechDebt
    //
    // The floor below is deliberately far lower than the live number of CALLS,
    // so an intentional consolidation does not fail this while a wholesale
    // disappearance does. It is a tripwire, not a tally -- which is why no
    // total is written down for it to drift from.
    const mints = walk(ADMIN).reduce(
      (n, f) =>
        n +
        (readFileSync(f, "utf8").match(/\bbeginRefresh\s*\(/g)?.length ?? 0),
      0,
    );
    expect(
      mints,
      `no beginRefresh call was found under ${ADMIN}. Either the hook was
replaced -- in which case this gate must follow it or be deleted -- or the scan
is looking in the wrong place. Until then every assertion below is vacuous.`,
    ).toBeGreaterThanOrEqual(6);
  });

  // THE DETECTOR MUST BE ABLE TO FAIL. Without these, a scan that matched
  // nothing would report every file clean and read as coverage.
  it.each([
    [
      "minted after an await",
      'const f = async () => { const a = await g(); const t = beginRefresh("x"); };',
    ],
    [
      "minted after an await in a later block",
      'const f = async () => { try { await g(); } catch {} const t = beginRefresh("x"); };',
    ],
    // THE WIDENING (#385). Every row below returned [] under the arrow-only
    // opener -- measured by running them against it, not assumed.
    [
      "inside an async function DECLARATION",
      'async function f() { const a = await g(); const t = beginRefresh("x"); }',
    ],
    [
      "a declaration whose PARAMETER LIST contains parentheses",
      'async function f(cb: () => void) { await g(); beginRefresh("x"); }',
    ],
    [
      "a declaration whose RETURN TYPE contains braces",
      'async function f(): Promise<{ n: number }> { await g(); beginRefresh("x"); }',
    ],
    [
      "a declaration with a return type and a catch -- the #385 handler's shape",
      'async function f(n: number): Promise<void> { try { await g(n); } catch { beginRefresh("x"); } }',
    ],
    // THE ARROW BRANCH'S OWN BALANCED SCAN. Under the negated character class
    // this row matched no opener at all and returned [] -- a false clean in
    // the direction the declaration branch had already closed.
    [
      "an ARROW whose parameter list contains parentheses",
      'const f = async (cb: () => void) => { await g(); beginRefresh("x"); };',
    ],
    [
      "an ARROW with a return type containing braces",
      'const f = async (): Promise<{ n: number }> => { await g(); beginRefresh("x"); };',
    ],
  ])("detects a late mint: %s", (_l, src) => {
    expect(lateMints(src).length).toBeGreaterThan(0);
  });

  it.each([
    [
      "minted at entry",
      'const f = async () => { const t = beginRefresh("x"); const a = await g(); };',
    ],
    ["no await at all", 'const f = () => { const t = beginRefresh("x"); };'],
    ["await but no mint", "const f = async () => { const a = await g(); };"],
    // The class that made the first version flag EVERYTHING: braces inside
    // comments and string literals broke the brace-balance walk, so one
    // function's body swallowed the rest of the file.
    [
      "a brace inside a comment",
      'const f = async () => { /* a } brace */ const t = beginRefresh("x"); await g(); };',
    ],
    [
      "a brace inside a string",
      'const f = async () => { const s = "a } brace"; const t = beginRefresh("x"); await g(); };',
    ],
    // BOTH HALVES OF THE WIDENING. Without these, a declaration opener that
    // flagged every declaration outright would satisfy the whole table above.
    [
      "a declaration minting at entry",
      'async function f() { const t = beginRefresh("x"); const a = await g(); }',
    ],
    [
      "a declaration with parens in its params, minting at entry",
      'async function f(cb: () => void) { const t = beginRefresh("x"); await g(); }',
    ],
    [
      "a declaration with no await",
      'async function f() { const t = beginRefresh("x"); }',
    ],
    // NOT A BODY. `declarationBodyStart` returns -1 rather than scanning on,
    // which would attribute a later statement's mints to this signature.
    [
      "an overload signature",
      'async function f(): Promise<void>;\nconst t = beginRefresh("x");',
    ],
    // BOTH HALVES of the arrow widening, so an arrow scan that flagged every
    // arrow outright would not satisfy the table above.
    [
      "an ARROW with parens in its params, minting at entry",
      'const f = async (cb: () => void) => { const t = beginRefresh("x"); await g(); };',
    ],
    [
      "a single-identifier arrow parameter",
      'const f = async x => { const t = beginRefresh("x"); await g(x); };',
    ],
  ])("does not flag: %s", (_l, src) => {
    expect(lateMints(src)).toEqual([]);
  });

  // "I COULD NOT LOOK" IS NOT "NOTHING TO COMPLAIN ABOUT".
  //
  // The brace walk used to `continue` on an unbalanced body under a comment
  // saying the emptiness guard would report it. That guard counts
  // `beginRefresh(` over RAW text against a floor, so a body skipped for
  // imbalance leaves the count unchanged and the guard cannot fire -- the
  // silent-success shape this repo keeps finding in its own tooling.
  it.each([
    [
      "an unterminated body",
      'const f = async () => { await g(); beginRefresh("x");',
    ],
  ])("reports a body it could not scan: %s", (_l, src) => {
    expect(unscannable(src).length).toBeGreaterThan(0);
    // And it is NOT reported as a clean scan.
    expect(lateMints(src)).toEqual([]);
  });

  it("does not report a balanced body as unscannable", () => {
    expect(
      unscannable('const f = async () => { await g(); beginRefresh("x"); };'),
    ).toEqual([]);
  });

  it("every admin component's async bodies can actually be scanned", () => {
    const blind = walk(ADMIN)
      .filter((f) => unscannable(readFileSync(f, "utf8")).length > 0)
      .map((f) => f.slice(f.indexOf("src")));

    expect(
      blind,
      `the brace walk never balanced inside these files, so their async bodies
were SKIPPED rather than found clean. A late mint in any of them is invisible
to the offender assertion below.`,
    ).toEqual([]);
  });

  it("no admin component mints a refresh token after an await", () => {
    const offenders = walk(ADMIN)
      .filter((f) => lateMints(readFileSync(f, "utf8")).length > 0)
      .map((f) => f.slice(f.indexOf("src")));

    expect(
      offenders,
      `these components call beginRefresh() after an await in the same async
function, so their tokens are ordered by when those awaits RESOLVED rather than
by invocation. A refresh started FIRST whose earlier fetch is slow then mints
the LATER token and overwrites a newer refresh's record. Move the mint to the
top of the function, above every await.`,
    ).toEqual([]);
  });
});
