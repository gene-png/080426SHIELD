import { describe, expect, it } from "vitest";

import {
  type RiskTargetUsed,
  TARGETS_NOT_RECORDED,
  targetSentences,
} from "./baseline";

/**
 * #474. The expected lines are the approved table's strings, verbatim
 * (advisor, #736 6054419744, approving 6053630989).
 *
 * RR-1 (#1122): each row carries the server's `label` (design note §6.2), and
 * the web renders it; WHEN a framework is named is decided once, on the
 * server, and pinned by the server-side label table there. This file's
 * naming cases (one ZT unnamed; CISA plus DoD named; CSF plus CISA plus DoD)
 * pinned the client-side count rule RR-1 deletes, and two of them #876's
 * two-ZT-in-one-register premise, so they are REPLACED (core principle 3) by
 * one case the deleted rule gets wrong.
 */
function t(
  kind: string,
  framework: string | null,
  target: number,
  source: string,
  label: string,
): RiskTargetUsed {
  return { kind, framework, target, source, origin: "live_at_generate", label };
}

const CSF_CLIENT_4 =
  "NIST CSF findings are measured against target tier 4, the engagement target when this register was generated.";
const CISA_CLIENT_4 =
  "Zero Trust (CISA ZTMM 2.0) findings are measured against target stage 4, the engagement target when this register was generated.";

describe("targetSentences (#474)", () => {
  it("one CSF, client 4", () => {
    expect(
      targetSentences([t("csf", null, 4, "client", "NIST CSF")], true),
    ).toEqual([CSF_CLIENT_4]);
  });

  it("one CSF, none set, and one CSF, unusable", () => {
    expect(
      targetSentences([t("csf", null, 3, "default", "NIST CSF")], true),
    ).toEqual([
      "NIST CSF findings are measured against target tier 3, SHIELD's default: no engagement target was set.",
    ]);
    expect(
      targetSentences(
        [t("csf", null, 3, "client_out_of_range", "NIST CSF")],
        true,
      ),
    ).toEqual([
      "NIST CSF findings are measured against target tier 3, SHIELD's default: the engagement target could not be used.",
    ]);
  });

  it("names the framework when the server's label does, with ONE ZT row (RR-1)", () => {
    // The register RR-1 writes for a CISA-and-DoD client with DoD left out:
    // one ZT row, which the server labels with its framework because the
    // register mentions two Zero Trust services (design note §6.2). The
    // deleted client-side rule counted ZT ROWS, so it printed a bare "Zero
    // Trust" here: this case goes red if that rule comes back.
    expect(
      targetSentences(
        [
          t("csf", null, 4, "client", "NIST CSF"),
          t("zt", "cisa_ztmm_2_0", 4, "client", "Zero Trust (CISA ZTMM 2.0)"),
        ],
        true,
      ),
    ).toEqual([CSF_CLIENT_4, CISA_CLIENT_4]);
  });

  it("says not recorded rather than nothing, for false and for absent", () => {
    expect(targetSentences([], false)).toEqual([TARGETS_NOT_RECORDED]);
    expect(targetSentences(undefined, undefined)).toEqual([
      TARGETS_NOT_RECORDED,
    ]);
    expect(TARGETS_NOT_RECORDED).toBe(
      "The targets these findings were measured against were not recorded for this register.",
    );
  });
});
