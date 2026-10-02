import { describe, expect, it } from "vitest";

import { targetFaultNote } from "./csf";
import { targetFault } from "./zt";

/**
 * #783: the client's dashboard and the client's documents describe a default
 * target in the same words.
 *
 * THIS TABLE IS DUPLICATED, word for word, in
 * `apps/api/tests/unit/test_target_source_in_deliverables.py`, which asserts
 * every sentence in the stored PDF, DOCX and XLSX and the `/results` summary.
 * The TS and Python sentences are synchronised, not derived: a fixture both
 * runners could read would close the window, and it needs the compose mount
 * tracked in #422. Change a sentence here and you must change it there.
 */
const TIER: Record<string, string> = {
  default: "Default target — no tier chosen at intake.",
  client_out_of_range: "Default target — the tier on file is not one CSF has.",
  client_below_floor:
    "Default target — the tier on file is a starting point, not a target.",
  client_unparseable: "Default target — the tier on file could not be read.",
  unrecognised: "Default target — the tier on file was not usable.",
};
const STAGE: Record<string, string> = {
  default: "Default target — no stage chosen at intake.",
  client_out_of_range:
    "Default target — the stage on file is not one this framework has.",
  client_below_floor:
    "Default target — the stage on file is a starting point, not a target.",
  client_unparseable: "Default target — the stage on file could not be read.",
  unrecognised: "Default target — the stage on file was not usable.",
};

/** The dashboards' lead-in, as `CsfDashboard` and `targetNote` write it. */
function sentence(note: string | null): string | null {
  return note === null ? null : `Default target — ${note}.`;
}

describe("the default-target sentences match the deliverables' (#783)", () => {
  it("says nothing for the client's own choice", () => {
    expect(targetFaultNote("client")).toBeNull();
    expect(targetFault("client")).toBeNull();
  });

  for (const [source, expected] of Object.entries(TIER)) {
    it(`CSF, ${source}`, () => {
      expect(sentence(targetFaultNote(source))).toBe(expected);
    });
  }

  for (const [source, expected] of Object.entries(STAGE)) {
    it(`ZT, ${source}`, () => {
      expect(sentence(targetFault(source))).toBe(expected);
    });
  }
});
