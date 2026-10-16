import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EnsureActiveClient } from "@/components/admin/EnsureActiveClient";

import { Dropzone } from "./Dropzone";

/**
 * #1262 (with #1129): an upload from an admin workspace is FILED under the
 * workspace's own client. The upload used the shared active-client cookie, so
 * with another tab on client B, a document dropped in client A's workspace was
 * stored under B. Through the REAL EnsureActiveClient and the real
 * `uploadArtifact`, with `fetch` stubbed per URL; the assertion is on the
 * upload request that leaves the browser. Outside a workspace (the client
 * wizard) the upload names no client, as before.
 */

const SERVICE = "00000000-0000-4000-8000-0000000005e1";
const CLIENT_A = "00000000-0000-4000-8000-00000000000a";

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

describe("Dropzone files an upload under its workspace's client (#1262)", () => {
  it("names the workspace's resolved client on the upload request", async () => {
    vi.stubGlobal("fetch", fetchMock);
    const onUploaded = vi.fn();
    const { container } = render(
      <EnsureActiveClient serviceId={SERVICE}>
        <Dropzone onUploaded={onUploaded} />
      </EnsureActiveClient>,
    );
    await screen.findByText(/drop/i);
    await dropFile(container);
    const urls = uploadUrls();
    expect(urls).toHaveLength(1);
    expect(
      new URL(urls[0], "http://localhost").searchParams.get("client_id"),
    ).toBe(CLIENT_A);
    expect(onUploaded).toHaveBeenCalledTimes(1);
  });

  it("names no client outside a workspace (the client wizard)", async () => {
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<Dropzone onUploaded={vi.fn()} />);
    await dropFile(container);
    const urls = uploadUrls();
    expect(urls).toHaveLength(1);
    expect(urls[0]).toBe("/api/proxy/artifacts");
  });
});
