import { afterEach, describe, expect, it, vi } from "vitest";

import { getClientName } from "./client";

/**
 * `getClientName` was the EIGHTH reader of `Client.legal_name` to turn a
 * nullable value into a display string with a bare `||`, and it was fixed with
 * nothing asserting the fix.
 *
 * Nothing could have caught it: `RiskRegisterDashboard.test.tsx` mocks this
 * function out entirely (`getClientName: vi.fn()`), there was no test file for
 * this module, and the Python sweep in
 * `test_self_serve_legal_name_contract.py` is rooted at `apps/api/app` — which
 * D-082 says itself, so the sweep cannot see the web layer by construction.
 *
 * The seventh reader got a rendered-bytes assertion precisely because a
 * resolver is not the surface. This is the eighth's.
 *
 * `jsonRequest` is module-private, so the seam is `fetch`. That is the more
 * primitive channel anyway: it exercises the real parse and the real `.find`
 * rather than a stub standing in for both.
 */

const CID = "00000000-0000-4000-8000-000000000001";

function mockClients(rows: Array<{ id: string; legal_name: string | null }>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      // `jsonRequest` calls `.json()` on the success path and `.text()` only
      // when `ok` is false. Both are provided so the mock cannot pass for the
      // wrong reason if that ordering ever changes.
      json: async () => rows,
      text: async () => JSON.stringify(rows),
    })) as unknown as typeof fetch,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("getClientName", () => {
  it("returns a real name unchanged", async () => {
    mockClients([{ id: CID, legal_name: "Atlas Defense Solutions" }]);
    await expect(getClientName(CID)).resolves.toBe("Atlas Defense Solutions");
  });

  // The three whitespace-ish spellings of "nobody has named this org". `"   "`
  // is the one a bare `||` lets through, and it is why this test exists: it
  // rendered as a blank Risk Register heading and inside "To synthesise risks
  // for ${clientName}, first complete: ...".
  it.each([null, "", "   "])(
    "labels an unnamed org rather than returning %o",
    async (blank) => {
      mockClients([{ id: CID, legal_name: blank as string | null }]);
      const name = await getClientName(CID);
      expect(name.trim().length).toBeGreaterThan(0);
      // The web's label for this state, not the API's "Client" — the two
      // surfaces are allowed to differ and D-082 says why.
      expect(name).toBe("(pending intake)");
    },
  );

  it("says 'Client' when the tenant is not in the list at all", async () => {
    // A DIFFERENT absence: we cannot identify the tenant, as opposed to
    // knowing it and finding it unnamed. Collapsing the two is what put one
    // word on both states.
    mockClients([{ id: "some-other-id", legal_name: "Someone Else" }]);
    await expect(getClientName(CID)).resolves.toBe("Client");
  });

  it("says 'Client' when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }) as unknown as typeof fetch,
    );
    // Same category as "not in the list": we do not know who this is.
    await expect(getClientName(CID)).resolves.toBe("Client");
  });
});
