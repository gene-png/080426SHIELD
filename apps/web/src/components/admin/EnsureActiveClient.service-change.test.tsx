import "@testing-library/jest-dom/vitest";

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EnsureActiveClient } from "./EnsureActiveClient";
import { useWorkspaceClientId } from "./workspaceClient";

/**
 * #1262, review of f9975caa: the client EnsureActiveClient provides belongs to
 * ONE service. If the same instance is handed a new `serviceId`, its children
 * must not keep seeing the old service's client while the new one resolves,
 * or an upload in that window is filed under the old client. Derived from the
 * service the id was resolved for, not reset on change, so there is no window.
 */

const SERVICE_1 = "00000000-0000-4000-8000-000000000001";
const SERVICE_2 = "00000000-0000-4000-8000-000000000002";
const CLIENT_1 = "00000000-0000-4000-8000-0000000000c1";

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function Probe(): React.JSX.Element {
  return <p>client:{useWorkspaceClientId() ?? "none"}</p>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EnsureActiveClient across a service change (#1262)", () => {
  it("never shows the previous service's client while the next one resolves", async () => {
    // Service 1 resolves; service 2's lookup never answers.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === `/api/proxy/admin/services/${SERVICE_1}`) {
          return json({ client_id: CLIENT_1 });
        }
        if (url === "/api/active-client") return json({ active: CLIENT_1 });
        return new Promise<Response>(() => undefined);
      }),
    );
    const { rerender } = render(
      <EnsureActiveClient serviceId={SERVICE_1}>
        <Probe />
      </EnsureActiveClient>,
    );
    expect(await screen.findByText(`client:${CLIENT_1}`)).toBeVisible();

    await act(async () => {
      rerender(
        <EnsureActiveClient serviceId={SERVICE_2}>
          <Probe />
        </EnsureActiveClient>,
      );
    });
    expect(screen.getByText("Opening workspace…")).toBeVisible();
    expect(screen.queryByText(`client:${CLIENT_1}`)).toBeNull();
  });
});
