import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EnsureActiveClient } from "@/components/admin/EnsureActiveClient";

import { Dropzone } from "./Dropzone";

/**
 * #1262, the `/intake` residual (review of 69fbc5b1): the Dropzone's own
 * `clientId` prop, the client the intake wizard loaded, reaches the upload
 * request outside a workspace, and a workspace's resolved client still wins
 * inside one. Through the REAL Dropzone and `uploadArtifact`, with `fetch`
 * stubbed per URL; the assertion is on the request that leaves the browser.
 */

const SERVICE = "00000000-0000-4000-8000-0000000005e1";
const CLIENT_A = "00000000-0000-4000-8000-00000000000a";
const CLIENT_W = "00000000-0000-4000-8000-0000000000c3";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
  if (url === `/api/proxy/admin/services/${SERVICE}`) {
    return json({ client_id: CLIENT_A });
  }
  if (url === "/api/active-client") return json({ active: CLIENT_A });
  if (url.startsWith("/api/proxy/artifacts") && init?.method === "POST") {
    return json(
      {
        id: "00000000-0000-4000-8000-0000000000d1",
        title: "a.csv",
        mime_type: "text/csv",
        size_bytes: 7,
        uploaded_at: "2026-10-16T00:00:00Z",
        origin: "client_upload",
      },
      201,
    );
  }
  throw new Error(`unexpected fetch ${init?.method ?? "GET"} ${url}`);
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockClear();
});

function uploadUrls(): string[] {
  return fetchMock.mock.calls
    .filter(
      (c) => (c as unknown as [string, RequestInit])[1]?.method === "POST",
    )
    .map((c) => String((c as unknown as [string])[0]));
}

async function dropFile(container: HTMLElement): Promise<void> {
  const input = container.querySelector(
    'input[type="file"]',
  ) as HTMLInputElement;
  expect(input, "no file input").not.toBeNull();
  const file = new File(["host,os"], "a.csv", { type: "text/csv" });
  await act(async () => {
    fireEvent.change(input, { target: { files: [file] } });
  });
}

function namedClient(url: string): string | null {
  return new URL(url, "http://localhost").searchParams.get("client_id");
}

describe("Dropzone names the client its prop gives (#1262, the /intake residual)", () => {
  it("files under its clientId prop outside a workspace", async () => {
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(
      <Dropzone onUploaded={vi.fn()} clientId={CLIENT_W} />,
    );
    await dropFile(container);
    const urls = uploadUrls();
    expect(urls).toHaveLength(1);
    expect(namedClient(urls[0])).toBe(CLIENT_W);
  });

  it("files under the workspace's client inside a workspace, over the prop", async () => {
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(
      <EnsureActiveClient serviceId={SERVICE}>
        <Dropzone onUploaded={vi.fn()} clientId={CLIENT_W} />
      </EnsureActiveClient>,
    );
    await screen.findByText(/drop/i);
    await dropFile(container);
    const urls = uploadUrls();
    expect(urls).toHaveLength(1);
    expect(namedClient(urls[0])).toBe(CLIENT_A);
  });
});
