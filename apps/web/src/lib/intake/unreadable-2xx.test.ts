import { afterEach, describe, expect, it, vi } from "vitest";

import { clientFacingError } from "@/lib/describe-save-error";

import { listArtifacts, uploadArtifact } from "./artifacts";
import {
  createAssessment,
  fetchAssessments,
  fetchIntake,
  submitIntake,
} from "./client";

/**
 * #1213, the intake sites (#1093 item 2's rule, applied to the twins). Our
 * proxy answers every 2xx with JSON, and an api 2xx it cannot read already
 * reaches the browser as the typed 504. So a 2xx whose body is not JSON came
 * from something in front of the app (a captive portal, a proxy's block page)
 * and the request may never have arrived.
 *
 * - A WRITE (submit, create, upload) must say its outcome is unknown, in the
 *   approved #550 sentence: never success, never a generic failure. Before,
 *   `res.json()` threw a bare SyntaxError and the caller showed its own
 *   failure copy ("Failed to submit intake.").
 * - A READ has no outcome to be unsure of: nothing was changed and nothing
 *   was loaded. It throws with its status and the raw body, so the caller's
 *   own load-failure copy applies, as for any failed load.
 */

const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

const PORTAL = "<html><body>Sign in to the network</body></html>";

function respondRaw(status: number, body: string): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { status })),
  );
}

async function caught(p: Promise<unknown>): Promise<unknown> {
  try {
    await p;
  } catch (err) {
    return err;
  }
  throw new Error("expected a rejection, got a result");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("intake writes: a 2xx we cannot read is an unknown outcome (#1213)", () => {
  it.each([
    [
      "submitIntake",
      () =>
        submitIntake({
          client: {},
          service_requests: [{ service_type: "tech_debt" }],
        }),
      "Failed to submit intake.",
    ],
    [
      "createAssessment",
      () => createAssessment({ service_type: "nist_csf" } as never),
      "Couldn't start the assessment.",
    ],
    [
      "uploadArtifact",
      () => uploadArtifact(new File(["x"], "a.txt", { type: "text/plain" })),
      "Upload failed.",
    ],
  ])("%s", async (_name, call, callerFallback) => {
    respondRaw(200, PORTAL);
    const err = await caught(call());
    expect(err).toMatchObject({ status: 200 });
    // What the caller shows: the #550 sentence, not its own failure copy.
    expect(clientFacingError(err, callerFallback)).toBe(OUTCOME_UNKNOWN);
  });
});

describe("intake reads: a 2xx we cannot read fails as a load (#1213)", () => {
  it.each([
    ["fetchIntake", () => fetchIntake()],
    ["fetchAssessments", () => fetchAssessments()],
    ["listArtifacts", () => listArtifacts()],
  ])("%s", async (_name, call) => {
    respondRaw(200, PORTAL);
    const err = await caught(call());
    expect(err).toMatchObject({ status: 200, payload: PORTAL });
    // Not a bare parse error, and no claim about an outcome.
    expect(err).not.toBeInstanceOf(SyntaxError);
    expect(clientFacingError(err, "Failed to load.")).toBe("Failed to load.");
  });
});
