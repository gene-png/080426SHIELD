import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIntakeAutoSave } from "./useIntakeAutoSave";

/**
 * IN-1 (#1049), ruling B (#736 6115773247): "Network error." only when no
 * response came back. When the api ANSWERED with a refusal that carries no
 * client copy (a `schema_*` 422), the sentence is the approved one below.
 *
 * Driven through the real `patchIntake` with `fetch` stubbed, so the error the
 * hook sees is the one production builds, not a fabricated shape.
 */

const REFUSED = "This value was not accepted, so it was not saved.";

function respond(status: number, body: unknown): void {
  respondRaw(status, JSON.stringify(body));
}

function respondRaw(status: number, body: string | null): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

/** A value the api still refuses after IN-1's https:// prefix (pinned as a
 *  422 by `test_intake_website_scheme.py`). "kentro.com" is now a 200, so a
 *  422 for it would be a state the system cannot produce. */
const REFUSED_INPUT = "not a website";

async function saveWebsite(): Promise<string | undefined> {
  const { result } = renderHook(() => useIntakeAutoSave());
  await act(async () => {
    await result.current.save({ client: { website: REFUSED_INPUT } });
  });
  const state = result.current.saveState;
  return state.kind === "error" ? state.message : undefined;
}

describe("useIntakeAutoSave refusal copy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("says the value was not accepted when the api refused it with a schema 422", async () => {
    // Captured from the api on 2026-10-12 (PATCH /intake through TestClient)
    // for {"client": {"website": "not a website"}}; only the correlation id
    // is dropped. `input` is the prefixed value the validator handed HttpUrl.
    respond(422, {
      error: {
        code: 422,
        message: "Request validation failed.",
        reason: "schema_url_parsing",
        reasons: ["schema_url_parsing"],
        details: [
          {
            type: "url_parsing",
            loc: ["body", "client", "website"],
            msg: "Input should be a valid URL, invalid international domain name",
            input: "https://not a website",
            ctx: { error: "invalid international domain name" },
          },
        ],
      },
    });
    const message = await saveWebsite();
    expect(message).toBe(REFUSED);
    expect(message).not.toContain("Network");
  });

  it("still says Network error when no response came back", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const message = await saveWebsite();
    expect(message).toBe("Network error.");
  });

  it("still shows the server's own sentence for a typed refusal", async () => {
    respond(409, {
      error: {
        reason: "intake_locked",
        message: "Intake was already submitted.",
      },
    });
    const message = await saveWebsite();
    expect(message).toBe("Intake was already submitted.");
  });

  // The 4xx/5xx boundary (review of #1092, item 3). `isAnsweredRefusal` is
  // `status >= 400 && status < 500`; widening it to `< 600` turns the 500
  // test red, narrowing it turns the empty-body 4xx test red.
  it("keeps today's Network error for a 500 with a non-JSON body (no 5xx copy is approved yet)", async () => {
    respondRaw(500, "Internal Server Error");
    const message = await saveWebsite();
    expect(message).toBe("Network error.");
  });

  it("says the value was not accepted for a 4xx with an empty body", async () => {
    respondRaw(400, null);
    const message = await saveWebsite();
    expect(message).toBe(REFUSED);
  });
});
