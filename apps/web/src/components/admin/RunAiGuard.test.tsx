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
    // `_ai_readiness`'s no-key branch, verbatim. It was an abbreviation
    // invented here, which is
    // the fixture-from-the-parser shape: a fixture written to what the reader
    // expects cannot express the reader and the server disagreeing.
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. Load a key to enable live AI.",
    can_configure: true,
    key_source: "none",
    serves: "offline",
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
    mockStatus(
      statusBody({ ready: true, key_source: "database", serves: "live" }),
    );
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
        JSON.stringify(
          statusBody({ ready: true, key_source: "database", serves: "live" }),
        ),
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
// branch is driven, and every row's text is one the old hardcoded sentence
// could never produce.
//
// The strings are copied from `routes/admin.py::_ai_readiness`, not from what
// the component does with them. **That is a hand duplication across a language
// boundary and nothing pins it:** reword a branch tomorrow and nothing here goes
// red, because every case asserts pass-through (`mockStatus(detail: x)` then
// `toHaveTextContent(x)`). Bounded rather than worthless -- pass-through is
// exactly what kills the hardcode mutant, which is the defect. The branch COUNT
// is pinned on the Python side.
//
// The labels carried `(admin.py:819)` and so on until review pointed out they sat
// two paragraphs from this repo's rule against citing line numbers. All five were
// correct and would have rotted on the next reflow of `admin.py`, inside test
// names. Find a branch by its quoted `detail` instead.
// ---------------------------------------------------------------------------

const READINESS_BRANCHES: ReadonlyArray<{
  label: string;
  body: Record<string, unknown>;
  detail: string;
  /** What a Run-AI does in this state (#472): canned output, or a failure. */
  serves: "offline" | "broken";
}> = [
  {
    label: "no key, for a provider whose key can be loaded here",
    body: { key_source: "none", can_configure: true },
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. Load a key to enable live AI.",
    serves: "offline",
  },
  {
    // #472: "Load a key" names a control that cannot work for vertex -- it
    // has no key, and the validator refuses one -- so its remedy is the mode.
    label: "no key, for a provider that authenticates without one",
    body: { key_source: "none", provider: "vertex", can_configure: false },
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. Provider 'vertex' authenticates without an API key, so there is none to load: set SHIELD_LLM_MODE=live and restart the api.",
    serves: "offline",
  },
  {
    // #472 round 1: openai uses a key, but only from the environment -- the
    // validator refuses a pasted one.
    label: "no key, for a provider whose key only the environment can carry",
    body: { key_source: "none", provider: "openai", can_configure: false },
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. A key for 'openai' cannot be loaded here: set OPENAI_API_KEY and SHIELD_LLM_MODE=live, then restart the api.",
    serves: "offline",
  },
  {
    // #472 round 1: telling a provider with no adapter to go live stops the
    // api booting.
    label: "no key, for a provider with no live adapter",
    body: { key_source: "none", provider: "bedrock", can_configure: false },
    detail:
      "No API key is loaded — AI steps will generate offline (fixture) responses. Provider 'bedrock' has no live adapter yet, so AI can only run offline: set SHIELD_LLM_PROVIDER to one of anthropic, gemini, openai, vertex.",
    serves: "offline",
  },
  {
    label: "env key but mode is not live",
    body: { key_source: "environment", mode: "fixture", can_configure: true },
    detail:
      "SHIELD_LLM_MODE='fixture', so AI steps generate offline (fixture) responses even though an environment key is present. Set SHIELD_LLM_MODE=live and restart the api, or load a key here to enable live AI without a redeploy.",
    serves: "offline",
  },
  {
    // The provider build REFUSES, and the server passes its message through.
    // This interpolation is `_build_provider`'s refusal of a stored key for
    // vertex. No UI step stores one today (`live_validate_key` admits
    // anthropic alone), and the other refusals -- live mode with no key, an
    // unimplemented provider -- are stopped at boot by the preflight. So this
    // row is reachable only past both, and is kept because the branch exists.
    label: "the provider build refuses",
    body: {
      key_source: "database",
      provider: "vertex",
      mode: "live",
      can_configure: false,
    },
    detail:
      "Run-AI will fail: A runtime API key is stored but provider 'vertex' has no key-based adapter (vertex uses ADC). Remove the stored key or switch SHIELD_LLM_PROVIDER.",
    serves: "broken",
  },
  {
    label: "anthropic SDK not importable",
    body: {
      key_source: "database",
      provider: "anthropic",
      can_configure: true,
    },
    detail:
      "Run-AI will fail: the 'anthropic' SDK is not importable in the api image.",
    serves: "broken",
  },
  {
    // `claude-opus-4-7` is the only member of `config.py`'s
    // `_KNOWN_PLACEHOLDER_MODELS`. An empty `SHIELD_LLM_MODEL` reaches this
    // branch too, and interpolates `''`.
    label: "model id is a known placeholder",
    body: {
      key_source: "database",
      model: "claude-opus-4-7",
      can_configure: true,
    },
    detail:
      "Run-AI will fail: SHIELD_LLM_MODEL='claude-opus-4-7' is not a usable model id — set a current model id and restart the api.",
    serves: "broken",
  },
];

/** A row whose copy says nothing about a missing key, found by label. */
const REFUSED = READINESS_BRANCHES.find(
  (b) => b.label === "the provider build refuses",
)!;

/** The status the server sends for one table row. */
function branchStatus(branch: (typeof READINESS_BRANCHES)[number]) {
  return statusBody({
    ...branch.body,
    detail: branch.detail,
    serves: branch.serves,
  });
}

describe("the warning states the server's own cause", () => {
  for (const branch of READINESS_BRANCHES) {
    it(`renders the detail for: ${branch.label}`, async () => {
      mockStatus(branchStatus(branch));
      renderGuard(vi.fn());

      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

      const dialog = await screen.findByRole("alertdialog");
      expect(dialog).toHaveTextContent(branch.detail);
    });
  }

  // REPLACES "says a key IS loaded on the four branches where one is" -- a
  // restatement, not a weakening, stated because core principle 3 requires
  // it. That test pinned the #471 copy "A key is loaded but ...". #472 made
  // the broken branches say what a Run-AI WILL DO ("Run-AI will fail: ...")
  // instead, which still never blames a missing key (pinned just below). The
  // property it is replaced with is the one #472 is about: "Continue offline"
  // promises the call stays offline, so it is offered on exactly the branches
  // where that is true.
  it("offers Continue offline on exactly the branches where the call IS offline (#472)", async () => {
    // Both kinds present, or the loop below proves one half only.
    expect(READINESS_BRANCHES.some((b) => b.serves === "offline")).toBe(true);
    expect(READINESS_BRANCHES.some((b) => b.serves === "broken")).toBe(true);

    for (const branch of READINESS_BRANCHES) {
      mockStatus(branchStatus(branch));
      const { unmount } = renderGuard(vi.fn());
      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
      const dialog = await screen.findByRole("alertdialog");
      const offered =
        screen.queryByRole("button", { name: "Continue offline" }) !== null;
      expect(offered, branch.label).toBe(branch.serves === "offline");
      // The sentence describing fixture output is true only of offline.
      const describesFixtures = (dialog.textContent ?? "").includes(
        "Offline (fixture) output is deterministic demo content",
      );
      expect(describesFixtures, branch.label).toBe(branch.serves === "offline");
      unmount();
      vi.restoreAllMocks();
    }
  });

  // #472 round 1: "Load a key" was rendered for every cause, including
  // providers whose key the validator refuses and one that has no key at all.
  // `can_configure` is the server's answer to "can a key be loaded here".
  it("offers Load a key only where a key can be loaded here", async () => {
    const both = new Set(READINESS_BRANCHES.map((b) => b.body.can_configure));
    expect(both).toEqual(new Set([true, false]));

    for (const branch of READINESS_BRANCHES) {
      mockStatus(branchStatus(branch));
      const { unmount } = renderGuard(vi.fn());
      fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
      await screen.findByRole("alertdialog");
      const offered =
        screen.queryByRole("link", { name: "Load a key" }) !== null;
      expect(offered, branch.label).toBe(branch.body.can_configure === true);
      unmount();
      vi.restoreAllMocks();
    }
  });

  // A RATCHET, and says so: from `_build_provider`, "offline" needs fixture
  // mode with no runtime key (source none/environment) and a fixture-mode
  // "broken" needs one (source database), so no reachable offline state and
  // broken state share a storage key today. The explicit `serves` check keeps
  // that true if the key or the states change.
  it("does not let an earlier offline acknowledgement wave through a broken configuration", async () => {
    // Same mode, provider, key source and `ready` as an acknowledged offline
    // state; only `serves` differs. The acknowledgement was a promise about
    // canned output, and a broken Run-AI is not that.
    const broken = READINESS_BRANCHES.find((b) => b.serves === "broken")!;
    mockStatus(statusBody({ ...broken.body, serves: "offline" }));
    const first = vi.fn();
    const { unmount } = renderGuard(first);
    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue offline" }),
    );
    expect(first).toHaveBeenCalledTimes(1);
    unmount();
    vi.restoreAllMocks();

    mockStatus(branchStatus(broken));
    const second = vi.fn();
    renderGuard(second);
    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(second).not.toHaveBeenCalled();
  });

  it("never asserts a missing key in the copy or the accessible name", async () => {
    // The accessible name is what a screen reader announces and what both e2e
    // specs select by. It named a cause that is wrong four times in five.
    const branch = REFUSED;
    mockStatus(branchStatus(branch));
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
      mockStatus(branchStatus(branch));
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

// ---------------------------------------------------------------------------
// THE DESCRIPTION WIRING, asserted because nothing asserted it.
//
// `aria-describedby` and the id it points at were added with no test. A typo in
// either half is silent in assistive tech and green everywhere else -- which is
// worse than not having it, because the entry claims the cause now reaches AT.
// ---------------------------------------------------------------------------

describe("the dialog's accessible description (#471)", () => {
  it("points aria-describedby at the element carrying the detail", async () => {
    const branch = REFUSED;
    mockStatus(branchStatus(branch));
    renderGuard(vi.fn());

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));

    const dialog = await screen.findByRole("alertdialog");
    const id = dialog.getAttribute("aria-describedby");
    expect(id, "the dialog has no aria-describedby").toBeTruthy();

    const described = document.getElementById(id!);
    expect(
      described,
      `aria-describedby points at id ${id!}, which no element has`,
    ).not.toBeNull();
    // The whole point: the DESCRIPTION is what carries the specific cause, since
    // the NAME has to stay constant to remain selectable.
    expect(described!.textContent).toBe(branch.detail);
  });

  it("renders the described element inside the dialog, so it cannot outlive it", async () => {
    // A description pointing at a node that unmounts while the dialog is open
    // would resolve to nothing. Both live in the same `{promptFor ? (` block;
    // this pins that rather than leaving it to a reading of the JSX.
    const branch = READINESS_BRANCHES[0];
    mockStatus(branchStatus(branch));
    renderGuard(vi.fn());

    fireEvent.click(screen.getByRole("button", { name: "Run AI" }));
    const dialog = await screen.findByRole("alertdialog");
    const id = dialog.getAttribute("aria-describedby")!;
    expect(
      dialog.querySelector(`#${id}`),
      "the described element is not inside the dialog",
    ).not.toBeNull();
  });
});
