import { describe, expect, it } from "vitest";

import {
  defaultChoice,
  includeFor,
  joinLabels,
  selectionLines,
  selectionModel,
} from "./selection";
import type { RiskSelectableService } from "./types";

/**
 * RR-1 (for #1122). Every expected string is copied from the design note's
 * §8 (rev 12), never from `selection.ts`'s own constants: a test reading the
 * constants it checks agrees with them by construction.
 */

const ATTACK: RiskSelectableService = {
  kind: "attack",
  service_id: "a",
  title: "ATT&CK",
  framework: null,
  label: "ATT&CK coverage",
};
const CSF: RiskSelectableService = {
  kind: "csf",
  service_id: "c",
  title: "CSF",
  framework: null,
  label: "NIST CSF",
};
const CISA: RiskSelectableService = {
  kind: "zt",
  service_id: "z1",
  title: "ZT",
  framework: "cisa_ztmm_2_0",
  label: "Zero Trust (CISA ZTMM 2.0)",
};
const DOD: RiskSelectableService = {
  kind: "zt",
  service_id: "z2",
  title: "ZT DoD",
  framework: "dod_ztra",
  label: "Zero Trust (DoD ZT Reference Architecture)",
};

describe("joinLabels", () => {
  it.each([
    [[], ""],
    [["A"], "A"],
    [["A", "B"], "A and B"],
    [["A", "B", "C"], "A, B and C"],
  ])("%j reads %j", (labels, expected) => {
    expect(joinLabels(labels)).toBe(expected);
  });
});

describe("selectionLines (copy 8, 9a-9c, 11)", () => {
  const COPY_11 =
    "This register has no usable record of how its services were chosen or which were left out.";

  it.each([
    ["absent", {}],
    ["false", { selection_recorded: false }],
  ])(
    "prints copy 11 alone when selection_recorded is %s",
    (_name, register) => {
      expect(selectionLines(register)).toEqual([COPY_11]);
    },
  );

  it("prints copy 11 and never copy 8, even with covered inputs present", () => {
    const lines = selectionLines({
      selection_recorded: false,
      covered_inputs: ["ATT&CK coverage", "NIST CSF"],
    });
    expect(lines).toEqual([COPY_11]);
    expect(lines.join(" ")).not.toMatch(/generated from/);
  });

  it("prints copy 8, the pinned literal", () => {
    expect(
      selectionLines({
        selection_recorded: true,
        covered_inputs: ["ATT&CK coverage", "NIST CSF"],
        deselected_inputs: [],
        ineligible_inputs: [],
      }),
    ).toEqual([
      "This register was generated from ATT&CK coverage and NIST CSF.",
    ]);
  });

  it("prints copy 8 then 9a for one deselected service", () => {
    expect(
      selectionLines({
        selection_recorded: true,
        covered_inputs: ["ATT&CK coverage", "Zero Trust (CISA ZTMM 2.0)"],
        deselected_inputs: ["Zero Trust (DoD ZT Reference Architecture)"],
      }),
    ).toEqual([
      "This register was generated from ATT&CK coverage and Zero Trust (CISA ZTMM 2.0).",
      "Zero Trust (DoD ZT Reference Architecture) was not included in this register.",
    ]);
  });

  it("prints 9b for two deselected services", () => {
    const lines = selectionLines({
      selection_recorded: true,
      covered_inputs: ["ATT&CK coverage", "NIST CSF"],
      deselected_inputs: ["Zero Trust (CISA ZTMM 2.0)", "Second"],
    });
    expect(lines[1]).toBe(
      "Zero Trust (CISA ZTMM 2.0) and Second were not included in this register.",
    );
    expect(lines).toHaveLength(2);
  });

  it("prints one 9c per ineligible service, after 9a", () => {
    expect(
      selectionLines({
        selection_recorded: true,
        covered_inputs: ["ATT&CK coverage", "NIST CSF"],
        deselected_inputs: ["Zero Trust (CISA ZTMM 2.0)"],
        ineligible_inputs: ["Zero Trust (DoD ZT Reference Architecture)"],
      }),
    ).toEqual([
      "This register was generated from ATT&CK coverage and NIST CSF.",
      "Zero Trust (CISA ZTMM 2.0) was not included in this register.",
      "Zero Trust (DoD ZT Reference Architecture) was engaged but had no assessment when this register was generated, so it is not in this register.",
    ]);
  });
});

describe("the selection block's model and request", () => {
  it("ticks every eligible service by default and leaves the radio unanswered", () => {
    const m = selectionModel([ATTACK, CSF, CISA, DOD], []);
    expect(defaultChoice(m)).toEqual({
      csf: true,
      zt: true,
      ztFramework: null,
    });
  });

  it("refuses to build a request while two frameworks are unanswered (copy 17)", () => {
    const m = selectionModel([ATTACK, CSF, CISA, DOD], []);
    expect(includeFor(m, defaultChoice(m))).toEqual({
      ok: false,
      reason: "zt_framework",
    });
  });

  it("sends the answered framework", () => {
    const m = selectionModel([ATTACK, CSF, CISA, DOD], []);
    expect(
      includeFor(m, { csf: true, zt: true, ztFramework: "dod_ztra" }),
    ).toEqual({ ok: true, include: { csf: true, zero_trust: "dod_ztra" } });
  });

  it("needs no radio answer once Zero Trust is unticked", () => {
    const m = selectionModel([ATTACK, CSF, CISA, DOD], []);
    expect(includeFor(m, { csf: true, zt: false, ztFramework: null })).toEqual({
      ok: true,
      include: { csf: true, zero_trust: null },
    });
  });

  it("takes the one framework from its row", () => {
    const m = selectionModel([ATTACK, CSF, CISA], []);
    expect(includeFor(m, defaultChoice(m))).toEqual({
      ok: true,
      include: { csf: true, zero_trust: "cisa_ztmm_2_0" },
    });
  });

  it("refuses ATT&CK alone (copy 5a)", () => {
    const m = selectionModel([ATTACK, CSF, CISA], []);
    expect(includeFor(m, { csf: false, zt: false, ztFramework: null })).toEqual(
      { ok: false, reason: "needs_csf_or_zt" },
    );
  });

  it("refuses when nothing but ATT&CK is eligible", () => {
    const m = selectionModel([ATTACK], []);
    expect(includeFor(m, defaultChoice(m))).toEqual({
      ok: false,
      reason: "needs_csf_or_zt",
    });
  });

  it.each([
    ["CSF only", [ATTACK, CSF], { csf: true, zero_trust: null }],
    ["ZT only", [ATTACK, CISA], { csf: false, zero_trust: "cisa_ztmm_2_0" }],
  ])(
    "requires the only one of CSF and ZT eligible (%s), even if unticked",
    (_name, eligible, include) => {
      const m = selectionModel(eligible, []);
      expect(
        includeFor(m, { csf: false, zt: false, ztFramework: null }),
      ).toEqual({ ok: true, include });
    },
  );

  it("never sends an ineligible service", () => {
    const m = selectionModel([ATTACK, CSF], [DOD]);
    expect(m.ineligible).toEqual([DOD]);
    expect(includeFor(m, defaultChoice(m))).toEqual({
      ok: true,
      include: { csf: true, zero_trust: null },
    });
  });
});
