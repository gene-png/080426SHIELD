import { describe, expect, it } from "vitest";

import { resolveClientChoice, type ReadState } from "./client-choice";

/**
 * RR-2 (for #1121), design note §3.1a: one test per row and per overlap. The
 * list fixtures are shaped like the API's `AdminClientListResponse`
 * (`apps/api/app/schemas/admin.py`), every field of `AdminClientSummary`
 * included, never like the resolver's own output.
 */
function summary(
  id: string,
  legal_name: string | null,
  dba_name: string | null = null,
) {
  return {
    id,
    legal_name,
    dba_name,
    industry: null,
    size_band: null,
    intake_completed_at: null,
    created_at: "2026-10-01T00:00:00Z",
    archived_at: null,
    open_request_count: 0,
    total_request_count: 0,
  };
}

const A = summary("aaaaaaaa-0000-4000-8000-000000000001", "Atlas Corp");
const B = summary(
  "bbbbbbbb-0000-4000-8000-000000000002",
  "Beacon LLC",
  "Beacon",
);
const UNLISTED = "cccccccc-0000-4000-8000-000000000003";

const ok = (value: unknown): ReadState => ({ state: "ok", value });
const PENDING: ReadState = { state: "pending" };
const FAILED: ReadState = { state: "failed" };
const many = ok({ clients: [A, B] });
const one = ok({ clients: [A] });
const empty = ok({ clients: [] });
const cookie = (active: unknown): ReadState => ok({ active });
const NO_URL = { present: false, value: null };
const url = (value: string) => ({ present: true, value });

describe("resolveClientChoice (§3.1a)", () => {
  it("row 0: list pending is loading, whatever the cookie and URL", () => {
    for (const c of [PENDING, FAILED, cookie(A.id)]) {
      for (const u of [NO_URL, url(A.id), url("")]) {
        expect(resolveClientChoice(PENDING, c, u).kind).toBe("loading");
      }
    }
  });

  it("row 0: many clients, cookie pending, no URL is loading, with the list's options", () => {
    const r = resolveClientChoice(many, PENDING, NO_URL);
    expect(r.kind).toBe("loading");
    expect(r.kind === "loading" && r.clients?.map((c) => c.id)).toEqual([
      A.id,
      B.id,
    ]);
  });

  it("row 1: list failed + cookie failed is list_failed", () => {
    expect(resolveClientChoice(FAILED, FAILED, NO_URL).kind).toBe(
      "list_failed",
    );
  });

  it("row 1: a 200 list body without `clients` is list_failed, never none", () => {
    expect(resolveClientChoice(ok({}), cookie(null), NO_URL).kind).toBe(
      "list_failed",
    );
    expect(
      resolveClientChoice(ok({ clients: "x" }), cookie(null), NO_URL).kind,
    ).toBe("list_failed");
  });

  it("row 1: URL unlisted + list failed is list_failed", () => {
    expect(resolveClientChoice(FAILED, cookie(null), url(UNLISTED)).kind).toBe(
      "list_failed",
    );
  });

  it("row 2: empty + cookie failed is none", () => {
    expect(resolveClientChoice(empty, FAILED, NO_URL).kind).toBe("none");
  });

  it("row 2: URL listed elsewhere + empty list is none", () => {
    expect(resolveClientChoice(empty, cookie(null), url(A.id)).kind).toBe(
      "none",
    );
  });

  it("row 3: URL listed wins over a cookie on another listed client", () => {
    const r = resolveClientChoice(many, cookie(A.id), url(B.id));
    expect(r).toMatchObject({
      kind: "chosen",
      client: { id: B.id, label: "Beacon (Beacon LLC)" },
    });
  });

  it("row 3: URL listed + cookie failed is chosen", () => {
    expect(resolveClientChoice(many, FAILED, url(B.id))).toMatchObject({
      kind: "chosen",
      client: { id: B.id },
    });
  });

  it("row 3: URL listed + stale cookie is chosen", () => {
    expect(
      resolveClientChoice(many, cookie(UNLISTED), url(A.id)),
    ).toMatchObject({
      kind: "chosen",
      client: { id: A.id, label: "Atlas Corp" },
    });
  });

  it("row 3: URL listed + cookie pending is chosen, NOT loading", () => {
    expect(resolveClientChoice(many, PENDING, url(A.id)).kind).toBe("chosen");
  });

  it("row 4a: URL unlisted + one client is link_unlisted, NOT the one client", () => {
    expect(resolveClientChoice(one, cookie(A.id), url(UNLISTED)).kind).toBe(
      "link_unlisted",
    );
  });

  it("row 4a: a never-listed id with many clients is link_unlisted", () => {
    expect(
      resolveClientChoice(many, cookie(A.id), url("not-a-client")).kind,
    ).toBe("link_unlisted");
  });

  it("row 4b: URL empty + cookie on a listed client is link_empty, NOT the cookie's", () => {
    expect(resolveClientChoice(many, cookie(A.id), url("")).kind).toBe(
      "link_empty",
    );
  });

  it("row 4b: an empty or bare ?client, with one client and with many, is link_empty", () => {
    for (const list of [one, many]) {
      for (const search of ["client=", "client"]) {
        const p = new URLSearchParams(search);
        const u = { present: p.has("client"), value: p.get("client") };
        expect(resolveClientChoice(list, cookie(null), u).kind).toBe(
          "link_empty",
        );
      }
    }
  });

  it("row 5: one client + stale cookie is chosen", () => {
    expect(resolveClientChoice(one, cookie(UNLISTED), NO_URL)).toMatchObject({
      kind: "chosen",
      client: { id: A.id },
    });
  });

  it("row 5: one client + cookie failed is chosen", () => {
    expect(resolveClientChoice(one, FAILED, NO_URL).kind).toBe("chosen");
  });

  it("row 5: one client + cookie pending is chosen, NOT loading", () => {
    expect(resolveClientChoice(one, PENDING, NO_URL).kind).toBe("chosen");
  });

  it("row 6: many + cookie read failed is cookie_failed", () => {
    expect(resolveClientChoice(many, FAILED, NO_URL).kind).toBe(
      "cookie_failed",
    );
  });

  it("row 6: many + a 200 `{}` body is cookie_failed, never unchosen", () => {
    expect(resolveClientChoice(many, ok({}), NO_URL).kind).toBe(
      "cookie_failed",
    );
  });

  it("row 6: many + `{active: 7}` is cookie_failed", () => {
    expect(resolveClientChoice(many, cookie(7), NO_URL).kind).toBe(
      "cookie_failed",
    );
  });

  it("row 7: the cookie names a listed client", () => {
    expect(resolveClientChoice(many, cookie(B.id), NO_URL)).toMatchObject({
      kind: "chosen",
      client: { id: B.id },
    });
  });

  it("row 8: the cookie names an unlisted id is stale", () => {
    expect(resolveClientChoice(many, cookie(UNLISTED), NO_URL).kind).toBe(
      "stale",
    );
  });

  it("row 9: no cookie is unchosen", () => {
    expect(resolveClientChoice(many, cookie(null), NO_URL).kind).toBe(
      "unchosen",
    );
  });

  // Carried from `lib/risk/client.test.ts`, deleted with `getClientName`
  // (RR-2, design note §6.2 item 3): a real name is used unchanged, and the
  // three spellings of "nobody has named this org" get the web's one label for
  // that state, never a blank heading. `"   "` is the one a bare `||` let
  // through. The other two cases there, "not in the list" and "the request
  // failed", are rows 4a/8 and row 1 above.
  it("uses a real name unchanged", () => {
    expect(resolveClientChoice(one, cookie(null), NO_URL)).toMatchObject({
      kind: "chosen",
      client: { label: "Atlas Corp" },
    });
  });

  it.each([null, "", "   "])(
    "labels an unnamed organisation rather than printing %o",
    (blank) => {
      const r = resolveClientChoice(
        ok({ clients: [summary(A.id, blank)] }),
        cookie(null),
        NO_URL,
      );
      expect(r).toMatchObject({
        kind: "chosen",
        client: { label: "(pending intake)" },
      });
    },
  );
});
