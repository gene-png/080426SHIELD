import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EnsureActiveClient } from "./EnsureActiveClient";
import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";

/**
 * #1129, review of f105cc30: through the REAL EnsureActiveClient, not a
 * hand-built provider. The page resolves its service's client and renders the
 * panel; the panel's list request and every Download link must name that
 * client, so a cookie another tab rewrote cannot pick what is listed or
 * downloaded. Every request is answered by `fetch` stubbed per URL.
 */

vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: null,
    phase: "error",
    settled: async () => null,
    refresh: () => undefined,
  }),
  hasAcknowledgedOffline: () => false,
  acknowledgeOffline: () => undefined,
}));

const SERVICE = "00000000-0000-4000-8000-0000000005e1";
const CLIENT_A = "00000000-0000-4000-8000-00000000000a";

const DOC = {
  id: "00000000-0000-4000-8000-0000000000d1",
  title: "a.csv",
  mime_type: "text/csv",
  size_bytes: 1024,
  uploaded_at: "2026-10-16T00:00:00Z",
  origin: "client_upload",
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn(async (url: string) => {
  if (url === `/api/proxy/admin/services/${SERVICE}`) {
    return json({ client_id: CLIENT_A });
  }
  // The cookie already names A when the page opens; another tab may rewrite
  // it later, which nothing below reads.
  if (url === "/api/active-client") return json({ active: CLIENT_A });
  if (url.startsWith("/api/proxy/artifacts")) return json({ items: [DOC] });
  throw new Error(`unexpected fetch ${url}`);
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockClear();
});

describe("IntakeDocumentsPanel inside the real EnsureActiveClient (#1129)", () => {
  it("lists and links documents for the workspace's resolved client", async () => {
    vi.stubGlobal("fetch", fetchMock);
    render(
      <EnsureActiveClient serviceId={SERVICE}>
        <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />
      </EnsureActiveClient>,
    );
    const link = await screen.findByRole("link", { name: "Download" });

    const listUrls = fetchMock.mock.calls
      .map((c) => String((c as unknown as [string])[0]))
      .filter((u) => u.startsWith("/api/proxy/artifacts"));
    expect(listUrls).toHaveLength(1);
    expect(
      new URL(listUrls[0], "http://localhost").searchParams.get("client_id"),
    ).toBe(CLIENT_A);

    const href = new URL(link.getAttribute("href") ?? "", "http://localhost");
    expect(href.pathname).toBe(`/api/proxy/artifacts/${DOC.id}/download`);
    expect(href.searchParams.get("client_id")).toBe(CLIENT_A);
  });

  it("links Download with no client_id outside a workspace (review of 5ae6bd01)", async () => {
    // No provider: the panel falls back to the cookie, and its link must be
    // the bare download path. An empty or "null" client_id would be refused
    // by the download proxy with a 400.
    vi.stubGlobal("fetch", fetchMock);
    render(
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
    );
    const link = await screen.findByRole("link", { name: "Download" });
    expect(link.getAttribute("href")).toBe(
      `/api/proxy/artifacts/${DOC.id}/download`,
    );
  });
});
