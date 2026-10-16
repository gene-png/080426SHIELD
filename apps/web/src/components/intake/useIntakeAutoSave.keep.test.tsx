import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIntakeAutoSave } from "./useIntakeAutoSave";

/**
 * #1115, the table approved on #736 (6207611148 items 6-8): the typed value
 * is let go (`onRefused`) only when the answer JUDGED it, a 400, 409 or 422.
 * A 401, 403 or 429, typed or not, said nothing about the value, so it is
 * kept, as is every 5xx and a network error. Driven through the real
 * `patchIntake` with `fetch` stubbed.
 */

const NOT_SAVED_KEPT =
  "This value was not saved. It is still in the form, so you can save it again.";
/** S-1115-2, a PLACEHOLDER until approved: the same answer for a field the
 *  wizard does not keep. */
const NOT_SAVED_RETYPE = "This value was not saved. Set it again to save it.";
const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

function respondRaw(status: number, body: string | null): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

async function save(): Promise<{
  refused: ReturnType<typeof vi.fn>;
  message: string | undefined;
}> {
  const refused = vi.fn();
  const { result } = renderHook(() => useIntakeAutoSave(undefined, refused));
  await act(async () => {
    await result.current.save({ client: { city: "Arlington" } });
  });
  const state = result.current.saveState;
  return {
    refused,
    message: state.kind === "error" ? state.message : undefined,
  };
}

describe("useIntakeAutoSave: which answers let the typed value go (#1115)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([400, 409, 422])(
    "lets it go on a %i, which judged the value",
    async (status) => {
      respondRaw(status, null);
      const { refused, message } = await save();
      expect(message).toBe("This value was not accepted, so it was not saved.");
      expect(refused).toHaveBeenCalledTimes(1);
      expect(refused).toHaveBeenCalledWith({ client: { city: "Arlington" } });
    },
  );

  it.each([401, 403, 429, 404])(
    "keeps it on an untyped %i, which did not judge the value",
    async (status) => {
      respondRaw(status, null);
      const { refused, message } = await save();
      expect(message).toBe(NOT_SAVED_KEPT);
      expect(refused).not.toHaveBeenCalled();
    },
  );

  it("does not say the value is in the form when the caller does not keep it (review of 8b4f28a1)", async () => {
    // Step 3's fields are re-read from the server when the step reopens, so
    // "It is still in the form" would be false for them.
    respondRaw(403, null);
    const refused = vi.fn();
    const { result } = renderHook(() =>
      useIntakeAutoSave(undefined, refused, () => false),
    );
    await act(async () => {
      await result.current.save({ phone: "555-0100" });
    });
    const state = result.current.saveState;
    expect(state.kind === "error" ? state.message : undefined).toBe(
      NOT_SAVED_RETYPE,
    );
    expect(refused).not.toHaveBeenCalled();
  });

  it("keeps it on the proxy's own 401, and shows its sentence", async () => {
    respondRaw(
      401,
      JSON.stringify({ error: { code: 401, message: "Not signed in." } }),
    );
    const { refused, message } = await save();
    expect(message).toBe("Not signed in.");
    expect(refused).not.toHaveBeenCalled();
  });

  it("keeps it on a typed 403 (ruling (b))", async () => {
    respondRaw(
      403,
      JSON.stringify({
        error: { code: 403, reason: "forbidden", message: "Not allowed." },
      }),
    );
    const { refused, message } = await save();
    expect(message).toBe("Not allowed.");
    expect(refused).not.toHaveBeenCalled();
  });

  it.each([502, 504])(
    "keeps it, and says the outcome is unknown, on a bare %i from in front of the api",
    async (status) => {
      respondRaw(status, "<html>Bad Gateway</html>");
      const { refused, message } = await save();
      expect(message).toBe(OUTCOME_UNKNOWN);
      expect(refused).not.toHaveBeenCalled();
    },
  );
});
