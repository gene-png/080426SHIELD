import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * A proxy must never turn an empty upstream body into `{}` at HTTP 200 (#173).
 *
 * ## What the defect was
 *
 * `return NextResponse.json(result ?? {});` in `attack/_proxy.ts` and
 * `ai/_proxy.ts`. An empty or absent upstream body became `{}` at **200**: the
 * client parsed it as its response type, every field was `undefined`, and the
 * renderer drew a successful response containing nothing.
 *
 * That is the silent under-report through a different door, one layer above the
 * place it was closed. `GET /attack/services/{id}/ai-inputs` exists precisely so
 * that "we dropped things" and "nothing was dropped" are not the same bytes; a
 * `?? {}` at the proxy makes "the upstream returned nothing" and "the upstream
 * returned an empty result" the same 200.
 *
 * ## Why this file is a guard and not a fix
 *
 * **The fix already shipped.** All six proxies replaced the coalesce with an
 * explicit 204 branch, and the comment beside it records the measurement that
 * made the removal safe -- the coalesce was also the only thing handling 204,
 * so deleting it without replacing it would have traded a swallow for a broken
 * path.
 *
 * What did NOT ship is anything that keeps it fixed. Nothing in the repo
 * imported a proxy helper or asserted a 204 before this file: six copies of a
 * hand-written branch, any of which a later reader could "simplify" back to
 * `?? {}` without knowing why it was there. The comment explains the reason and
 * the comment is not a mechanism -- `CLAUDE.md`: the reflex survives the rule
 * until the rule has a gate.
 *
 * ## Derived, not listed
 *
 * The proxy set is read off the directory, so a seventh is covered the day it
 * is added rather than the day someone remembers this file. #173's own scope
 * line says "every ATT&CK and AI proxy route" and the fix went wider than that
 * -- csf, zt, risk and tech-debt have the same shape and were fixed with it.
 * Enumerating the two the issue named would have pinned a third of the set.
 *
 * **What this does NOT prove:** that a real 204 reaches a browser as a 204.
 * That needs a running upstream, and none of the SIX PROXIED routers (attack,
 * csf, zt, risk, tech_debt, ai) emits one today -- the measurement is in the
 * proxies' own comments. Other routers do: `routes/admin.py` returns
 * `HTTP_204_NO_CONTENT` behind the admin proxies, and `routes/auth.py`'s only
 * one is `/auth/logout`, which no proxy fronts. (This sentence said "no route
 * emits one", which was false; #318.) This pins the SOURCE, which is where the
 * regression would be written.
 *
 * ## A floor, not a census
 *
 * The coalesce patterns below catch `?? {}` / `|| []` (with an optional
 * parenthesis), `() => ({})`, `() => { return {} }`, `?? null` in a helper,
 * and `?? null` inside a `NextResponse.json(...)` anywhere. NOT modelled:
 * `Promise.resolve({})`, a spread `{ ...result }`, `Object.assign({}, x)`, an
 * `async` arrow returning `{}`, or an empty value built in a variable first.
 *
 * ## Matched against CODE, not text
 *
 * Every pattern below runs on the source with comments removed. The proxies'
 * own comments quote the forbidden shape (`result ?? {}`) and the required one
 * (`status: 204`), so a text match was satisfied, or tripped, by prose: one
 * reworded comment could make the 204 assertion permanently true (#318).
 */

/**
 * The source with `//` and block comments removed, string and template
 * literals kept (a `//` inside `"http://..."` is not a comment).
 */
function code(src: string): string {
  let out = "";
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    const n = src[i + 1];
    if (c === '"' || c === "'" || c === "`") {
      let j = i + 1;
      while (j < src.length && src[j] !== c) j += src[j] === "\\" ? 2 : 1;
      out += src.slice(i, j + 1);
      i = j + 1;
    } else if (c === "/" && n === "/") {
      while (i < src.length && src[i] !== "\n") i += 1;
    } else if (c === "/" && n === "*") {
      const end = src.indexOf("*/", i + 2);
      i = end === -1 ? src.length : end + 2;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

const PROXY_ROOT = join(process.cwd(), "src/app/api/proxy");

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...sourceFiles(p));
    else if (entry.endsWith(".ts") && !entry.endsWith(".test.ts")) out.push(p);
  }
  return out;
}

const FILES = sourceFiles(PROXY_ROOT);
const HELPERS = FILES.filter((p) => p.endsWith("_proxy.ts"));

/** Relative label, so a failure names the file rather than a machine path. */
const label = (p: string) => p.slice(p.indexOf("api/proxy"));

describe("proxies never synthesise an empty result", () => {
  it("finds the proxy sources at all", () => {
    // Fail loudly rather than sweep nothing. Moving or renaming the directory
    // must not read as "every proxy is fine" -- "I could not look" and "nothing
    // to complain about" are the two branches this repo keeps collapsing.
    expect(FILES.length).toBeGreaterThan(6);
    expect(HELPERS.length).toBeGreaterThanOrEqual(6);
  });

  it.each(FILES.map((p) => [label(p), p] as const))(
    "%s does not coalesce a missing body into a JSON response",
    (name, path) => {
      const src = code(readFileSync(path, "utf8"));
      // An over-eager comment strip would leave nothing to match and pass in
      // silence: every route and helper file exports its handlers, so the
      // stripped code must still say so.
      expect(
        /\bexport\b/.test(src),
        `${name}: nothing left after stripping comments`,
      ).toBe(true);
      // The SHAPE, not the literal that was there, and ANYWHERE in the code,
      // not only inside `NextResponse.json(...)`: `const body = result ?? {}`
      // two lines above the response, `.catch(() => ({}))`, and
      // `.catch(() => { return {}; })` reintroduce the defect and passed the
      // narrower pattern (#318). `?? null` is the same defect answering `null`
      // at 200; it is forbidden in the response itself here, and anywhere in a
      // helper below, because `accessToken ?? null` is a legitimate use in
      // route files.
      const coalesced = new RegExp(
        [
          String.raw`(\?\?|\|\|)\s*\(?\s*(\{\s*\}|\[\s*\])`,
          String.raw`=>\s*\(\s*(\{\s*\}|\[\s*\]|null)\s*\)`,
          String.raw`=>\s*\{\s*return\s+(\{\s*\}|\[\s*\]|null)\s*;?\s*\}`,
          String.raw`NextResponse\.json\([^;]*(\?\?|\|\|)\s*\(?\s*null\b`,
        ].join("|"),
      ).exec(src);
      expect(
        coalesced?.[0] ?? null,
        `${name} answers 200 with a synthesised empty body. The client then
parses it as its response type, every field is undefined, and the renderer draws
a successful response containing nothing — "the upstream returned nothing" and
"the upstream returned an empty result" become the same 200. That is #173.`,
      ).toBeNull();
    },
  );

  it.each(HELPERS.map((p) => [label(p), p] as const))(
    "%s handles an empty upstream body explicitly",
    (name, path) => {
      const src = code(readFileSync(path, "utf8"));
      // The other half, and asserting only the first would let a "fix" that
      // deleted the coalesce and nothing else pass — which trades a swallow for
      // a path that answers `null` at 200, or throws. `CLAUDE.md`: before
      // fixing an over-match, check what it was accidentally catching.
      //
      // The BRANCH, not two words anywhere: the 204 must be the answer to
      // `result === undefined` and to nothing else. A 204 returned for a
      // genuine empty object (`{}` becoming "no content") is the reverse of
      // #173 and passed the old check (#318).
      expect(
        /\bNextResponse\b/.test(src),
        `${name}: no NextResponse left after stripping comments`,
      ).toBe(true);
      const branch =
        /if\s*\(\s*result\s*===\s*undefined\s*\)\s*\{\s*return\s+new\s+NextResponse\(\s*null\s*,\s*\{\s*status:\s*204\s*\}\s*\)\s*;?\s*\}/;
      expect(
        branch.test(src),
        `${name} has no \`result === undefined\` branch answering 204. The coalesce
this test forbids was also the only thing handling 204, so removing it without
replacing it is not a fix.`,
      ).toBe(true);
      const answers204 = (src.match(/status:\s*204/g) ?? []).length;
      expect(
        answers204,
        `${name}: expected exactly one 204 response, found ${answers204}. A second one
answers "no content" for something other than an empty upstream body -- the
reverse of #173.`,
      ).toBe(1);
      // In a helper, `?? null` anywhere is the #173 defect answering `null`.
      const nulled = /(\?\?|\|\|)\s*\(?\s*null\b/.exec(src);
      expect(
        nulled?.[0] ?? null,
        `${name} coalesces the upstream result to null`,
      ).toBeNull();
    },
  );
});
