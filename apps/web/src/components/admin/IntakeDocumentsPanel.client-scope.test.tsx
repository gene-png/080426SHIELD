import "@testing-library/jest-dom/vitest";

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";
import { WorkspaceClientProvider } from "./workspaceClient";

/**
 * #1129: the panel's document list is scoped to the workspace's OWN client,
 * the one EnsureActiveClient resolved for this page, not to the shared
 * active-client cookie. Another tab can rewrite the cookie after this page
 * mounted; a `reloadKey` change must still ask for this workspace's client.
 * Through the real `listArtifacts` with `fetch` stubbed, so the assertion is
 * on the request that leaves the browser.
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

const CLIENT_A = "00000000-0000-4000-8000-00000000000a";

const fetchMock = vi.fn(
  async () =>
    new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
);

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockClear();
});

function listUrls(): string[] {
  return fetchMock.mock.calls
    .map((c) => String((c as unknown as [string])[0]))
    .filter((u) => u.startsWith("/api/proxy/artifacts"));
}

function panel(reloadKey: number) {
  return (
    <WorkspaceClientProvider clientId={CLIENT_A}>
      <IntakeDocumentsPanel
        onExtract={() => undefined}
        extracting={false}
        reloadKey={reloadKey}
      />
    </WorkspaceClientProvider>
  );
}

describe("IntakeDocumentsPanel asks for its workspace's client (#1129)", () => {
  it("names the workspace's client on mount and on every reload", async () => {
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(panel(0));
    expect(await screen.findByText("No client documents")).toBeVisible();
    // Another tab rewrites the cookie here; nothing the panel sends reads it.
    await act(async () => {
      rerender(panel(1));
    });
    const urls = listUrls();
    expect(urls).toHaveLength(2);
    for (const u of urls) {
      expect(new URL(u, "http://localhost").searchParams.get("client_id")).toBe(
        CLIENT_A,
      );
    }
  });
});
