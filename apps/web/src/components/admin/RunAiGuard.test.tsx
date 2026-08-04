import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RunAiGuard } from "./RunAiGuard";

/**
 * Issue 2: the Run-AI gate. The behaviour the user asked for specifically is
 * the last test here — after the API key is removed, the NEXT Run AI in the
 * same session must warn again, even though the admin already clicked
 * "Continue offline" earlier in that session.
 */

function statusBody(over: Record<string, unknown> = {}) {
  return {
    mode: "fixture",
    provider: "anthropic",
    model: "claude-opus-5",
    ready: false,
    detail: "No API key is loaded.",
    can_configure: true,
    key_source: "none",
    ...over,
  };
}

function mockStatus(body: Record<string, unknown>) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

function renderGuard(onProceed: () => void) {
  return render(
    <RunAiGuard onProceed={onProceed}>
      {({ onClick }) => (
        <button type="button" onClick={onClick}>
          Run AI
        </button>
      )}
    </RunAiGuard>,
  );
}

describe("RunAiGuard (issue 2)", () => {
  it("runs straight through when AI is live — no extra click in the happy path", async () => {
    mockStatus(statusBody({ ready: true, key_source: "database" }));
    const onProceed = vi.fn();
    renderGuard(onProceed);

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    await waitFor(() => expect(onProceed).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("warns instead of running when no key is loaded", async () => {
    mockStatus(statusBody());
    const onProceed = vi.fn();
    renderGuard(onProceed);
    // Let the status load before clicking.
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(onProceed).not.toHaveBeenCalled();
    expect(
      screen.getByText(/generate an offline response/i),
    ).toBeInTheDocument();
  });

  it("proceeds after the admin knowingly continues offline, and doesn't re-warn", async () => {
    mockStatus(statusBody());
    const onProceed = vi.fn();
    const { unmount } = renderGuard(onProceed);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue offline" }),
    );
    expect(onProceed).toHaveBeenCalledTimes(1);

    // Second run in the same session: no dialog, straight through.
    unmount();
    const second = vi.fn();
    renderGuard(second);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    await waitFor(() => expect(second).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("warns AGAIN on the first Run AI after the key is removed", async () => {
    // Session 1: a key is loaded and AI is live, so nothing is acknowledged.
    // Then the admin acknowledges offline mode under a DIFFERENT config.
    mockStatus(statusBody());
    const first = vi.fn();
    const { unmount } = renderGuard(first);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue offline" }),
    );
    expect(first).toHaveBeenCalledTimes(1);
    unmount();
    vi.restoreAllMocks();

    // The admin loads a key (config changes), then removes it again. The
    // post-removal status differs from the acknowledged one — here the removal
    // leaves an environment key behind, a different key_source — so the stale
    // acknowledgement must not apply.
    mockStatus(statusBody({ key_source: "environment" }));
    const afterRemoval = vi.fn();
    renderGuard(afterRemoval);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(
      afterRemoval,
      "a removed/changed key must re-warn, not reuse the old acknowledgement",
    ).not.toHaveBeenCalled();
  });

  it("fails open when the status endpoint is unavailable — never blocks work", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    const onProceed = vi.fn();
    renderGuard(onProceed);

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    await waitFor(() => expect(onProceed).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
