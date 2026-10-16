import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { patchIntake } from "@/lib/intake/client";

import { useIntakeAutoSave } from "./useIntakeAutoSave";

/**
 * #1093 item 2: a save that LANDED must not read as "Network error.".
 *
 * - A 2xx whose body is not JSON: `patchIntake` used to throw a bare
 *   SyntaxError with no status, which the hook classed as no answer at all.
 *   Our proxy never sends one, so it came from in front of the app and the
 *   save may or may not have landed: the outcome is unknown, not "Saved".
 * - A throw from the caller's `onUpdate` sat inside the save's `try`, so a bug
 *   in the caller was reported to the client as a failed save. It must fail
 *   loudly instead, as itself.
 *
 * Driven through the real `patchIntake` with `fetch` stubbed.
 */

function respondRaw(status: number, body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

describe("patchIntake: a 2xx with an unreadable body", () => {
  it("throws with the 2xx status, not a bare parse error", async () => {
    respondRaw(200, "OK");
    await expect(
      patchIntake({ client: { city: "Arlington" } }),
    ).rejects.toMatchObject({ status: 200, payload: "OK" });
  });
});

describe("useIntakeAutoSave: a save that landed (#1093 item 2)", () => {
  it("says the outcome is unknown, keeps the value and updates nothing, for a 2xx it cannot read", async () => {
    // Review of e85890b3: our proxy answers every 2xx with JSON, and an
    // unreadable api 2xx already reaches the browser as the typed 504. So a
    // non-JSON 2xx came from something in front of the app (a captive portal,
    // a proxy's block page) and the PATCH may never have arrived: "Saved"
    // would be a false success.
    respondRaw(200, "<html>Sign in to the network</html>");
    const onUpdate = vi.fn();
    const onRefused = vi.fn();
    const { result } = renderHook(() =>
      useIntakeAutoSave(onUpdate, onRefused, () => true),
    );
    let returned: unknown = "unset";
    await act(async () => {
      returned = await result.current.save({ client: { city: "Arlington" } });
    });
    expect(result.current.saveState).toEqual({
      kind: "error",
      message: OUTCOME_UNKNOWN,
    });
    expect(returned).toBeNull();
    expect(onUpdate).not.toHaveBeenCalled();
    expect(onRefused).not.toHaveBeenCalled();
  });

  it("fails loudly, as itself, when the caller's onUpdate throws", async () => {
    respondRaw(200, JSON.stringify({ client: null, service_requests: [] }));
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const onUpdate = vi.fn(() => {
      throw new Error("caller bug");
    });
    const { result } = renderHook(() =>
      useIntakeAutoSave(onUpdate, undefined, () => true),
    );
    let thrown: unknown = null;
    await act(async () => {
      try {
        await result.current.save({ client: { city: "Arlington" } });
      } catch (e) {
        thrown = e;
      }
    });
    expect(thrown).toBeInstanceOf(Error);
    expect((thrown as Error).message).toBe("caller bug");
    // The save itself landed: the header must not say it failed.
    expect(result.current.saveState).not.toMatchObject({
      kind: "error",
      message: "Network error.",
    });
    expect(result.current.saveState.kind).toBe("saved");
    expect(error).toHaveBeenCalledWith(
      expect.stringContaining("[intake] onUpdate threw"),
      expect.any(Error),
    );
  });
});
