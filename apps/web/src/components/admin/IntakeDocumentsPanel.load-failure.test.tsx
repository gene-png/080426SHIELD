import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";

/**
 * #1223 item 2: a failed document list rendered the error's own message,
 * `ArtifactUploadError`'s "Upload failed: <status>", for a READ. #1225 item 1:
 * nor may it render a plain-string api `detail` ("X-Client-Id header is
 * required for this role."), which carries no `reason` and is internal text.
 * Only a TYPED sentence (D-016 `{reason, message}`) is shown; otherwise the
 * panel's own load-failure copy. Through the real `listArtifacts` with `fetch` stubbed.
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

  it("keeps #550's outcome sentence off this read (RR-2)", async () => {
    respond(
      504,
      JSON.stringify({
        error: {
          code: 504,
          reason: "upstream_outcome_unknown",
          message:
            "We couldn't confirm whether this finished. It may still complete; check before trying again.",
        },
      }),
    );
    render(
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't load documents.",
    );
    expect(screen.queryByText(/couldn't confirm/)).toBeNull();
  });

  it.each([
    [
      "an untyped 400 (current_client's plain detail)",
      400,
      JSON.stringify({
        error: {
          code: 400,
          message: "X-Client-Id header is required for this role.",
        },
      }),
      "X-Client-Id",
    ],
    [
      "an untyped 503 sentence",
      503,
      JSON.stringify({ error: { code: 503, message: "Storage is offline." } }),
      "Storage is offline.",
    ],
    ["a raw 500 body", 500, "Internal Server Error", "Internal Server Error"],
  ])(
    "shows its own copy, not internal server text, on %s (#1225)",
    async (_n, status, body, internal) => {
      respond(status, body);
      render(
        <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "Couldn't load documents.",
      );
      expect(screen.queryByText(new RegExp(internal))).toBeNull();
    },
  );

  it("shows a TYPED server sentence (D-016 {reason, message})", async () => {
    respond(
      409,
      JSON.stringify({
        error: {
          code: 409,
          reason: "client_archived",
          message: "This client has been archived.",
        },
      }),
    );
    render(
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This client has been archived.",
    );
  });
});
