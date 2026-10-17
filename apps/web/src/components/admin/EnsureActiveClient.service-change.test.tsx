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

  it("does not carry one service's error to the next (#1266)", async () => {
    const CLIENT_2 = "00000000-0000-4000-8000-0000000000c2";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === `/api/proxy/admin/services/${SERVICE_1}`) {
          return new Response("{}", { status: 500 });
        }
        if (url === `/api/proxy/admin/services/${SERVICE_2}`) {
          return json({ client_id: CLIENT_2 });
        }
        if (url === "/api/active-client") return json({ active: CLIENT_2 });
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    const { rerender } = render(
      <EnsureActiveClient serviceId={SERVICE_1}>
        <Probe />
      </EnsureActiveClient>,
    );
    expect(await screen.findByRole("alert")).toBeVisible();

    await act(async () => {
      rerender(
        <EnsureActiveClient serviceId={SERVICE_2}>
          <Probe />
        </EnsureActiveClient>,
      );
    });
    expect(await screen.findByText(`client:${CLIENT_2}`)).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("never writes the cookie for a lookup a newer service superseded (#1266)", async () => {
    const CLIENT_2 = "00000000-0000-4000-8000-0000000000c2";
    let releaseService1: (r: Response) => void = () => undefined;
    const posted: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === `/api/proxy/admin/services/${SERVICE_1}`) {
          return new Promise<Response>((resolve) => {
            releaseService1 = resolve;
          });
        }
        if (url === `/api/proxy/admin/services/${SERVICE_2}`) {
          return json({ client_id: CLIENT_2 });
        }
        if (url === "/api/active-client" && init?.method === "POST") {
          posted.push(
            (JSON.parse(String(init.body)) as { clientId: string }).clientId,
          );
          return json({ ok: true });
        }
        // The cookie names neither, so every current lookup writes it.
        if (url === "/api/active-client") return json({ active: null });
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    const { rerender } = render(
      <EnsureActiveClient serviceId={SERVICE_1}>
        <Probe />
      </EnsureActiveClient>,
    );
    // Switch before service 1's lookup answers; service 2 opens.
    await act(async () => {
      rerender(
        <EnsureActiveClient serviceId={SERVICE_2}>
          <Probe />
        </EnsureActiveClient>,
      );
    });
    expect(await screen.findByText(`client:${CLIENT_2}`)).toBeVisible();
    // Now the stale lookup answers. It must not write the cookie.
    await act(async () => {
      releaseService1(json({ client_id: CLIENT_1 }));
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(posted).toEqual([CLIENT_2]);
    expect(screen.getByText(`client:${CLIENT_2}`)).toBeVisible();
  });

  it("never writes the cookie when the switch lands during the advisory read (#1266, review of 02a26f52)", async () => {
    const CLIENT_2 = "00000000-0000-4000-8000-0000000000c2";
    let releaseRead1: (r: Response) => void = () => undefined;
    let reads = 0;
    const posted: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === `/api/proxy/admin/services/${SERVICE_1}`) {
          return json({ client_id: CLIENT_1 });
        }
        if (url === `/api/proxy/admin/services/${SERVICE_2}`) {
          return json({ client_id: CLIENT_2 });
        }
        if (url === "/api/active-client" && init?.method === "POST") {
          posted.push(
            (JSON.parse(String(init.body)) as { clientId: string }).clientId,
          );
          return json({ ok: true });
        }
        if (url === "/api/active-client") {
          reads += 1;
          // Service 1's advisory read is held open; service 2's answers.
          if (reads === 1) {
            return new Promise<Response>((resolve) => {
              releaseRead1 = resolve;
            });
          }
          return json({ active: null });
        }
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    const { rerender } = render(
      <EnsureActiveClient serviceId={SERVICE_1}>
        <Probe />
      </EnsureActiveClient>,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(reads).toBe(1);
    await act(async () => {
      rerender(
        <EnsureActiveClient serviceId={SERVICE_2}>
          <Probe />
        </EnsureActiveClient>,
      );
    });
    expect(await screen.findByText(`client:${CLIENT_2}`)).toBeVisible();
    await act(async () => {
      releaseRead1(json({ active: null }));
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(posted).toEqual([CLIENT_2]);
  });

  it("aborts a cookie write already in flight when the service changes (#1266, review of 02a26f52)", async () => {
    const CLIENT_2 = "00000000-0000-4000-8000-0000000000c2";
    const signals: AbortSignal[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === `/api/proxy/admin/services/${SERVICE_1}`) {
          return json({ client_id: CLIENT_1 });
        }
        if (url === `/api/proxy/admin/services/${SERVICE_2}`) {
          return json({ client_id: CLIENT_2 });
        }
        if (url === "/api/active-client" && init?.method === "POST") {
          const body = JSON.parse(String(init.body)) as { clientId: string };
          if (body.clientId === CLIENT_1) {
            // Service 1's write is in flight when the switch happens.
            if (init.signal) signals.push(init.signal);
            return new Promise<Response>(() => undefined);
          }
          return json({ ok: true });
        }
        if (url === "/api/active-client") return json({ active: null });
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    const { rerender } = render(
      <EnsureActiveClient serviceId={SERVICE_1}>
        <Probe />
      </EnsureActiveClient>,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(signals).toHaveLength(1);
    expect(signals[0].aborted).toBe(false);
    await act(async () => {
      rerender(
        <EnsureActiveClient serviceId={SERVICE_2}>
          <Probe />
        </EnsureActiveClient>,
      );
    });
    expect(signals[0].aborted).toBe(true);
    expect(await screen.findByText(`client:${CLIENT_2}`)).toBeVisible();
  });

  it("clears a service's error once that service succeeds (#1266, review of 02a26f52)", async () => {
    const CLIENT_2 = "00000000-0000-4000-8000-0000000000c2";
    let service1Calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === `/api/proxy/admin/services/${SERVICE_1}`) {
          service1Calls += 1;
          return service1Calls === 1
            ? new Response("{}", { status: 500 })
            : json({ client_id: CLIENT_1 });
        }
        if (url === `/api/proxy/admin/services/${SERVICE_2}`) {
          return json({ client_id: CLIENT_2 });
        }
        if (url === "/api/active-client") return json({ active: null });
        throw new Error(`unexpected fetch ${url}`);
      }),
    );
    const view = (id: string) => (
      <EnsureActiveClient serviceId={id}>
        <Probe />
      </EnsureActiveClient>
    );
    const { rerender } = render(view(SERVICE_1));
    expect(await screen.findByRole("alert")).toBeVisible();
    await act(async () => {
      rerender(view(SERVICE_2));
    });
    expect(await screen.findByText(`client:${CLIENT_2}`)).toBeVisible();
    await act(async () => {
      rerender(view(SERVICE_1));
    });
    expect(await screen.findByText(`client:${CLIENT_1}`)).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
