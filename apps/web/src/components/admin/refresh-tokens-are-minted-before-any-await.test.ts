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
 * The opener pattern (see `lateMints` below) requires the literal `=>`
 * after the parameter list, so it matches async ARROW FUNCTIONS ONLY. The
 * pattern is deliberately NOT quoted here: writing a regex into prose is
 * how this file acquired an invisible BACKSPACE byte while this very
 * paragraph was being written, which is the defect
 * `check_no_control_chars.py` exists for. Read it at the definition.
 *
 * An `async function` DECLARATION is invisible to it, and
 * `ZtWorkspace.tsx` alone has six that contain awaits:
 * `onCreateAssessment`, `onAnswerUpdate`, `onApprove`, `onDiscard`,
 * `onChangeTargetStage`, `onRunAi`. A late mint inside any of them is not
 * reported.
 *
 * That is not hypothetical: those handlers are where the NEXT tokens are owed.
 * `onChangeTargetStage` and its CSF twin currently await a gap fetch with no
 * token and no catch at all (filed), so the fix for that defect is precisely
 * the code this gate cannot see.
 *
 * Widening the opener to cover declarations is the fix and is deliberately not
 * made here -- it changes what this gate reports across four workspaces, which
 * belongs in the PR that adds the tokens rather than in one correcting a
 * comment.
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

/** Offsets of every `beginRefresh(` that follows an `await` in its own async body. */
export function lateMints(raw: string): number[] {
  const src = codeOnly(raw);
  const bad: number[] = [];
  const opener = /\basync\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = opener.exec(src)) !== null) {
    let depth = 1;
    let i = m.index + m[0].length;
    const start = i;
    for (; i < src.length && depth > 0; i++) {
      if (src[i] === "{") depth++;
      else if (src[i] === "}") depth--;
    }
    if (depth !== 0) continue; // unbalanced: the emptiness guard reports it
    const body = src.slice(start, i - 1);
    const firstAwait = body.search(/\bawait\b/);
    if (firstAwait === -1) continue;
    const mintRe = /\bbeginRefresh\s*\(/g;
    let g: RegExpExecArray | null;
    while ((g = mintRe.exec(body)) !== null) {
      if (g.index > firstAwait) bad.push(start + g.index);
    }
  }
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
  ])("does not flag: %s", (_l, src) => {
    expect(lateMints(src)).toEqual([]);
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
