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
    // admin.py:819, verbatim. It was an abbreviation invented here, which is
    // the fixture-from-the-parser shape: a fixture written to what the reader
    // expects cannot express the reader and the server disagreeing.
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. Load a key to enable live AI.",
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
    // CHANGED, AND NOT WEAKENED -- stated explicitly because core principle 3
    // requires saying so. This asserted `/generate an offline response/i`, the
    // tail of the sentence the component HARDCODED for all five not-ready
    // causes. That sentence is the defect: it named a missing key as the reason
    // in the four cases where a key is loaded. An assertion pinning it was
    // pinning the bug.
    //
    // The replacement is strictly stronger: it requires the server's own
    // sentence for THIS branch, sourced from `routes/admin.py` rather than from
    // whatever the component happens to render.
    expect(
      screen.getByText(/AI steps will generate offline \(fixture\) responses/i),
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

  it("does NOT run when clicked before the status has loaded — it waits, then warns", async () => {
    // The full-suite e2e failure this pins: under load the ai-status fetch had
    // not resolved when Run AI was clicked, the guard treated "not asked yet"
    // as "unknown, fail open", and 1646 fields of canned output were written
    // with no warning at all. "Still loading" is not "unavailable".
    let resolveStatus!: (r: Response) => void;
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveStatus = resolve;
      }),
    );
    const onProceed = vi.fn();
    renderGuard(onProceed);

    // Click while the status request is still in flight.
    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    expect(
      onProceed,
      "a click made before the status is known must not produce canned output",
    ).not.toHaveBeenCalled();

    // The answer arrives: no key loaded. The deferred click must now warn.
    resolveStatus(
      new Response(JSON.stringify(statusBody()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(onProceed).not.toHaveBeenCalled();
  });

  it("honours a deferred click when the status turns out to be live", async () => {
    let resolveStatus!: (r: Response) => void;
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveStatus = resolve;
      }),
    );
    const onProceed = vi.fn();
    renderGuard(onProceed);

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    expect(onProceed).not.toHaveBeenCalled();

    resolveStatus(
      new Response(
        JSON.stringify(statusBody({ ready: true, key_source: "database" })),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    // No warning is owed when AI is live — the click just lands late.
    await waitFor(() => expect(onProceed).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// THE WARNING NAMES THE SERVER'S CAUSE, NOT A HARDCODED ONE.
//
// `_ai_readiness` has FIVE not-ready branches. This modal rendered one
// sentence -- "No API key is loaded" -- for all five, and FOUR of them mean a
// key IS loaded. A consultant who had loaded a key read a cause they knew was
// false, dismissed the warning, and the run served fixture content into a
// client deliverable.
//
// ONE CASE WOULD PROVE NOTHING. A component that hardcodes whatever string it
// is handed passes any single case; that is the mutation-sampling problem --
// drawing the expected value from inside the region already covered. So every
// branch is driven, and the discriminating ones are the four whose text
// contains "A key is loaded" / "key is present", which the old component could
// never produce.
//
// The strings are copied from `routes/admin.py::_ai_readiness`, not from what
// the component does with them.
// ---------------------------------------------------------------------------

const READINESS_BRANCHES: ReadonlyArray<{
  label: string;
  body: Record<string, unknown>;
  detail: string;
  /** True for the four branches that say a key IS loaded. */
  contradictsTheOldCopy: boolean;
}> = [
  {
    label: "no key at all (admin.py:819)",
    body: { key_source: "none" },
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. Load a key to enable live AI.",
    contradictsTheOldCopy: false,
  },
  {
    label: "env key but mode is not live (admin.py:840)",
    body: { key_source: "environment", mode: "fixture" },
    detail:
      "SHIELD_LLM_MODE='fixture', so AI steps generate offline (fixture) responses even though an environment key is present. Set SHIELD_LLM_MODE=live and restart the api, or load a key here to enable live AI without a redeploy.",
    contradictsTheOldCopy: true,
  },
  {
    label: "provider has no adapter (admin.py:852)",
    body: { key_source: "database", provider: "mistral" },
    detail:
      "A key is loaded but provider 'mistral' has no runtime adapter — use anthropic, openai, or gemini.",
    contradictsTheOldCopy: true,
  },
  {
    label: "anthropic SDK not importable (admin.py:860)",
    body: { key_source: "database", provider: "anthropic" },
    detail:
      "A key is loaded but the 'anthropic' SDK is not importable in the api image.",
    contradictsTheOldCopy: true,
  },
  {
    label: "model id is a placeholder (admin.py:868)",
    body: { key_source: "database", model: "your-model-here" },
    detail:
      "A key is loaded, but SHIELD_LLM_MODEL='your-model-here' is not a usable model id — set a current model id and restart the api.",
    contradictsTheOldCopy: true,
  },
];

describe("the warning states the server's own cause", () => {
  for (const branch of READINESS_BRANCHES) {
    it(`renders the detail for: ${branch.label}`, async () => {
      mockStatus(statusBody({ ...branch.body, detail: branch.detail }));
      renderGuard(vi.fn());

      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

      const dialog = await screen.findByRole("alertdialog");
      expect(dialog).toHaveTextContent(branch.detail);
    });
  }

  it("says a key IS loaded on the four branches where one is", async () => {
    // The assertion the old component could never satisfy, stated once over
    // the whole set rather than per case -- so ADDING a sixth branch that says
    // "a key is loaded" and forgetting to drive it cannot pass here silently.
    const contradicting = READINESS_BRANCHES.filter(
      (b) => b.contradictsTheOldCopy,
    );
    expect(contradicting).toHaveLength(4);

    for (const branch of contradicting) {
      mockStatus(statusBody({ ...branch.body, detail: branch.detail }));
      const { unmount } = renderGuard(vi.fn());
      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
      const dialog = await screen.findByRole("alertdialog");
      expect(dialog.textContent ?? "").toMatch(/key is loaded|key is present/);
      unmount();
      vi.restoreAllMocks();
    }
  });

  it("never asserts a missing key in the copy or the accessible name", async () => {
    // The accessible name is what a screen reader announces and what both e2e
    // specs select by. It named a cause that is wrong four times in five.
    const branch = READINESS_BRANCHES[3];
    mockStatus(statusBody({ ...branch.body, detail: branch.detail }));
    renderGuard(vi.fn());

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveAttribute("aria-label", "AI is not ready to run live");
    expect(dialog.textContent ?? "").not.toMatch(/No API key is loaded/);
    // The imperative that was false on this branch.
    expect(dialog.textContent ?? "").not.toMatch(/Load a key to run real AI/);
  });

  it("keeps the accessible name CONSTANT across branches", async () => {
    // A name derived from `detail` would be more specific and would make the
    // dialog unselectable by name -- both e2e specs and `acknowledgeOfflineAi`
    // find it that way. Pinned so the next person reaching for "derive the
    // aria-label too" sees why it is not derived.
    const names: string[] = [];
    for (const branch of READINESS_BRANCHES) {
      mockStatus(statusBody({ ...branch.body, detail: branch.detail }));
      const { unmount } = renderGuard(vi.fn());
      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
      const dialog = await screen.findByRole("alertdialog");
      names.push(dialog.getAttribute("aria-label") ?? "");
      unmount();
      vi.restoreAllMocks();
    }
    expect(new Set(names).size).toBe(1);
  });
});
