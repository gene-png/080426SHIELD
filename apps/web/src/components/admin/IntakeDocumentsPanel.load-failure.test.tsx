import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";

/**
 * #1223 item 2: a failed document list rendered the error's own message,
 * `ArtifactUploadError`'s "Upload failed: <status>", for a READ. It now shows
 * the server's sentence when there is one and the panel's own load-failure
 * copy otherwise. Through the real `listArtifacts` with `fetch` stubbed.
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

function respond(status: number, body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("IntakeDocumentsPanel: the document list failed to load (#1223)", () => {
  it.each([
    ["a bare 500", 500, ""],
    ["an unreadable 2xx", 200, "<html>Sign in to the network</html>"],
  ])(
    "shows the panel's own copy on %s, never the error's message",
    async (_n, status, body) => {
      respond(status, body);
      render(
        <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Couldn't load documents.",
      );
      expect(screen.queryByText(/Upload failed/)).toBeNull();
    },
  );

  it("shows the server's own sentence when it sent one", async () => {
    respond(
      503,
      JSON.stringify({ error: { code: 503, message: "Storage is offline." } }),
    );
    render(
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Storage is offline.",
    );
  });
});
