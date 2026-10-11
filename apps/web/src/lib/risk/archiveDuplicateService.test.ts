import { afterEach, describe, expect, it, vi } from "vitest";

import { archiveDuplicateService, RiskProxyError } from "./client";

/**
 * #896 review B2: the banner archives through the Risk-scoped route, which
 * re-checks on the server that the service is still one of a duplicate group.
 * The helper rejects with the status and the parsed body. The screen shows the
 * API's own sentence where there is one, its fallback when the API answered
 * without one, and reports the outcome as unconfirmed when there was no
 * answer at all -- a null (non-JSON) body among them (#896 R3-3).
 */

const fetchMock = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
});

function stub(res: Response): void {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(res);
  vi.stubGlobal("fetch", fetchMock);
}

describe("archiveDuplicateService (#896)", () => {
  it("POSTs to the client's Risk archive route and resolves on 204", async () => {
    stub(new Response(null, { status: 204 }));
    await expect(archiveDuplicateService("c1", "svc-2")).resolves.toBe(
      undefined,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/proxy/risk/clients/c1/services/svc-2/archive");
    expect(init.method).toBe("POST");
  });

  it("rejects with the status and the parsed body", async () => {
    const body = {
      error: {
        code: 409,
        reason: "service_not_in_duplicate_group",
        message: "m",
      },
    };
    stub(new Response(JSON.stringify(body), { status: 409 }));
    const err = await archiveDuplicateService("c1", "svc-2").catch(
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(RiskProxyError);
    expect(err).toMatchObject({ status: 409, payload: body });
  });

  it("rejects with a null body when the body is not JSON", async () => {
    stub(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(archiveDuplicateService("c1", "svc-2")).rejects.toMatchObject({
      status: 502,
      payload: null,
    });
  });
});
