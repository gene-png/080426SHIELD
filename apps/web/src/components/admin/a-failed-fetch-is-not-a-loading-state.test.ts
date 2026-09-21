import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * No admin workspace swallows a fetch failure into a state that reads as
 * "still loading" (#292).
 *
 * ## The shape
 *
 * A component fetches, sets state on success, and catches with a comment:
 *
 *     } catch {
 *       // Non-blocking; the score/gap panels show their own loading state.
 *     }
 *
 * The comment is the defect, not the excuse. The panels DO show a loading
 * state, and it is indistinguishable from a slow network — so a consultant
 * looking at a permanently-spinning card cannot tell in-flight from failed
 * from never-attempted. `CLAUDE.md`: a value that is `null` for BOTH "still
 * loading" and "request failed" makes its callers conflate the two.
 *
 * ## Two sub-shapes, and the second is worse
 *
 * Most of these leave an AMBIGUITY. Two asserted a known NEGATIVE: the
 * deliverable catches said the card "shows 'not finalized yet'", which is a
 * claim about the SERVER made on the strength of a request that failed, and a
 * consultant can act on it by finalizing a second time. Missing data defaults
 * to unconfirmed, never to a known negative.
 *
 * ## Derived, because the issue's list was a sample
 *
 * #292 named four sites. Sweeping the SHAPE — a `try` that sets state whose
 * `catch` neither reverts nor surfaces — found twelve across the repo, nine of
 * them in these four workspaces. A guard over the four files would go stale on
 * the fifth workspace; this reads the directory.
 */

const ADMIN = join(process.cwd(), "src/components/admin");

/**
 * BOTH extensions. The first version collected `.tsx` only, which silently
 * exempted every `.ts` in the same directory -- including `useRefreshFailures.ts`,
 * the hook this whole fix is built on. A guard that cannot see the file it
 * depends on is the selector-that-selects-nothing shape, one directory in.
 */
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

const FILES = walk(ADMIN);

/**
 * Strip comments, PRESERVING string and template literals.
 *
 * This is not fastidiousness, it is the second defect this guard had. The
 * first rewrite scanned raw source, so it flagged FOUR files whose only
 * offence was a docstring *describing* the defect -- every workspace here
 * documents the original `} catch {}` in its header comment. A guard that
 * fires on prose about the bug is no more usable than one that misses the bug.
 *
 * A naive global strip is the other trap: `"https://x"` becomes `"https:` and
 * the resulting unbalanced quote or brace produces a different false positive.
 * So this walks the source tracking which construct it is inside.
 */
function stripComments(src: string): string {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (c === "/" && next === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }
    if (c === "/" && next === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i += 2;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      out += c;
      i++;
      while (i < src.length) {
        if (src[i] === "\\") {
          out += src[i] + (src[i + 1] ?? "");
          i += 2;
          continue;
        }
        out += src[i];
        if (src[i] === quote) {
          i++;
          break;
        }
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
 * Every `catch` whose body does nothing, DERIVED rather than spelled.
 *
 * The first version of this guard was a single regex:
 *
 *     /\}\s*catch\s*\{\s*(?:\/\/[^\n]*\n\s*)+\}/
 *
 * and it was **narrower than the four hand-written tests it replaced**. The
 * `(?:...)+` requires at least one `//` line, so it matched the comment-only
 * anonymous catch and NOTHING ELSE. Run against the forms it is named for:
 *
 *     } catch {}                  -> PASSED CLEAN   <- the form all four
 *     } catch (err) { ... }       -> PASSED CLEAN      workspace docstrings
 *     .catch(() => null)          -> PASSED CLEAN      name as THE defect
 *
 * That was found by RUNNING the regex, not by reading it -- a derivation sold
 * as more general than an enumeration, and strictly less, which is the mirror
 * of the shape this file exists to catch.
 *
 * So: strip comments, find each `catch`, take its body by brace balance, and
 * ask whether anything is left. Binding or no binding, comments or none.
 */
function silentCatches(src: string): string[] {
  const code = stripComments(src);
  const found: string[] = [];
  const opener = /\bcatch\s*(?:\([^)]*\))?\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = opener.exec(code)) !== null) {
    let depth = 1;
    let i = m.index + m[0].length;
    for (; i < code.length && depth > 0; i++) {
      if (code[i] === "{") depth++;
      else if (code[i] === "}") depth--;
    }
    // Unbalanced braces mean we cannot read this file's structure. FAIL
    // CLOSED: report it rather than skipping it, because "I could not look"
    // must not share a branch with "nothing to complain about".
    if (depth !== 0) {
      found.push("<unparseable catch block>");
      break;
    }
    if (code.slice(m.index + m[0].length, i - 1).trim() === "") {
      found.push(m[0]);
    }
  }
  return found;
}

/**
 * The promise-chain spelling of the same swallow. `.catch(() => null)` is not
 * a `catch` block at all, so no amount of widening the block scanner reaches
 * it -- it is a separate class and gets its own detector.
 */
const SWALLOWING_CHAIN =
  /\.catch\s*\(\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*(?:null|undefined|\{\s*\}|\[\s*\]|void 0)\s*\)/;

function swallows(src: string): boolean {
  return silentCatches(src).length > 0 || SWALLOWING_CHAIN.test(stripComments(src));
}

describe("admin workspaces never present a failed fetch as an ongoing load", () => {
  it("finds the admin components at all", () => {
    // Fail closed. A moved or renamed directory would otherwise turn every
    // assertion below into zero cases, which vitest reports as success.
    expect(FILES.length).toBeGreaterThanOrEqual(15);
  });

  // THE GUARD MUST BE ABLE TO FAIL, and this is the assertion that says so.
  //
  // The previous version was green over three of the four defect forms it was
  // named for, and nothing in the suite could tell. A detector with no
  // known-bad corpus is a claim about its author's imagination; this table is
  // the CLASSES, so widening the detector later cannot quietly narrow it.
  it.each([
    ["bare anonymous", "try { a(); } catch {}"],
    ["bare, newline", "try { a(); } catch {\n}"],
    ["bare with binding", "try { a(); } catch (err) {}"],
    ["comment-only anonymous", "try { a(); } catch {\n  // nothing\n}"],
    ["comment-only with binding", "try { a(); } catch (e) {\n  // nothing\n}"],
    ["block comment only", "try { a(); } catch {\n  /* nothing */\n}"],
    ["chain to null", "load().catch(() => null);"],
    ["chain to undefined", "load().catch((e) => undefined);"],
    ["chain to empty object", "load().catch(() => {});"],
  ])("detects a swallow written as: %s", (_label, sample) => {
    expect(swallows(sample)).toBe(true);
  });

  it.each([
    ["a catch that reverts", "try { a(); } catch { setX(null); }"],
    ["a catch that surfaces", "try { a(); } catch (e) {\n  // why\n  note(e);\n}"],
    ["a chain that handles", "load().catch((e) => note(e));"],
    // The false positive the first rewrite shipped: every workspace here
    // DOCUMENTS the original defect in its header comment, so a scanner that
    // reads raw source flags the four files it was written to protect.
    [
      "a block comment describing the defect",
      "/* old code was } catch {} and it was wrong */ function f() {}",
    ],
    [
      "a line comment describing the defect",
      ["// was: } catch {}", "try { a(); } catch (e) { note(e); }"].join("\n"),
    ],
    // The other trap: a naive strip turns a URL in a string into an
    // unterminated quote, which produces a DIFFERENT false positive.
    [
      "a url in a string literal",
      'const u = "https://example.com/a"; try { a(); } catch (e) { note(e); }',
    ],
  ])("does not flag: %s", (_label, sample) => {
    expect(swallows(sample)).toBe(false);
  });

  it("no component swallows a failure", () => {
    const offenders = FILES.filter((f) => swallows(readFileSync(f, "utf8"))).map(
      (f) => f.slice(f.indexOf("src")),
    );

    expect(
      offenders,
      `these admin components catch a failure and neither revert nor surface it,
so the panel is left in a state a consultant reads as "still loading". Set a
refresh-error state and render it; "non-blocking" is not the same as silent.`,
    ).toEqual([]);
  });
});
