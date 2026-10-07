import { afterEach, describe, expect, it, vi } from "vitest";

import { archiveService } from "./client";

/**
 * #896: the client helper the Risk Register's archive button calls. It
 * rejects with the status and the parsed body, so the screen can show the
 * API's own sentence where there is one and its fallback otherwise.
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

describe("archiveService (#896)", () => {
  it("sends DELETE to the service proxy and resolves on 204", async () => {
    stub(new Response(null, { status: 204 }));
    await expect(archiveService("svc-2")).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/admin/services/svc-2", {
      method: "DELETE",
    });
  });

  it("rejects with the status and the parsed body", async () => {
    const body = {
      error: { code: 504, reason: "upstream_outcome_unknown", message: "m" },
    };
    stub(new Response(JSON.stringify(body), { status: 504 }));
    await expect(archiveService("svc-2")).rejects.toMatchObject({
      status: 504,
      payload: body,
    });
  });

  it("rejects with a null body when the body is not JSON", async () => {
    stub(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(archiveService("svc-2")).rejects.toMatchObject({
      status: 502,
      payload: null,
    });
  });
});
