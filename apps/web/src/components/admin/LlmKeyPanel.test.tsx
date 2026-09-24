import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LlmKeyPanel } from "./LlmKeyPanel";

/**
 * #472 round 1: removing the stored key said "AI steps will generate offline
 * responses again" whatever happened next. In live mode an ENVIRONMENT key
 * takes over, and Run-AI keeps calling the provider with the client's data --
 * so the notice has to come from the status re-read after the removal.
 */

function status(over: Record<string, unknown>) {
  return {
    mode: "live",
    provider: "anthropic",
    model: "claude-opus-5",
    ready: true,
    detail: "Live AI configured (anthropic/claude-opus-5).",
    can_configure: true,
    key_source: "database",
    serves: "live",
    ...over,
  };
}

function stubApi(afterRemoval: Record<string, unknown>) {
  let removed = false;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/admin/llm-key") && init?.method === "DELETE") {
      removed = true;
      return new Response(null, { status: 204 });
    }
    if (url.endsWith("/admin/ai-status")) {
      return new Response(JSON.stringify(removed ? afterRemoval : status({})), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
}

async function removeTheKey() {
  render(<LlmKeyPanel />);
  fireEvent.click(await screen.findByRole("button", { name: "Remove key" }));
  fireEvent.click(await screen.findByRole("button", { name: "Yes, remove" }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LlmKeyPanel's removal notice (#472)", () => {
  it("does not say offline when an environment key keeps AI live", async () => {
    stubApi(status({ key_source: "environment" }));
    await removeTheKey();
    await waitFor(() =>
      expect(screen.getByText(/Key removed/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Key removed/)).not.toHaveTextContent(/offline/i);
    expect(screen.getByText(/Key removed/)).toHaveTextContent(/still live/i);
    // Not "on the environment key": for vertex it would be ADC. The detail
    // above says which (round 2 on #472).
    expect(screen.getByText(/Key removed/)).not.toHaveTextContent(
      /environment key/i,
    );
  });

  it("says offline when the call really is offline now", async () => {
    stubApi(
      status({
        mode: "fixture",
        ready: false,
        key_source: "none",
        serves: "offline",
        detail: "No API key is loaded",
      }),
    );
    await removeTheKey();
    await waitFor(() =>
      expect(screen.getByText(/Key removed/)).toHaveTextContent(/offline/i),
    );
  });
});

// #472 round 2: the panel's paste form rendered for every provider, directly
// under server copy saying a key cannot be loaded here -- a control that
// cannot work, beside the sentence saying so.
describe("LlmKeyPanel's paste form", () => {
  function stubStatus(body: Record<string, unknown>) {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }

  it("is offered where a key can be loaded here", async () => {
    stubStatus(status({ key_source: "none", ready: false, serves: "offline" }));
    render(<LlmKeyPanel />);
    expect(
      await screen
        .findByRole("textbox", { name: "Provider API key" })
        .catch(() => screen.findByLabelText("Provider API key")),
    ).toBeInTheDocument();
  });

  it("is withheld where one cannot, and says so", async () => {
    stubStatus(
      status({
        provider: "openai",
        key_source: "none",
        ready: false,
        serves: "offline",
        can_configure: false,
      }),
    );
    render(<LlmKeyPanel />);
    expect(
      await screen.findByText(/cannot be loaded here/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Provider API key")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save key" })).toBeNull();
  });
});
