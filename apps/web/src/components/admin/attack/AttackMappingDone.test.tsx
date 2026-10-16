import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CatalogTechnique } from "@/lib/attack/types";

import { AttackMappingDone } from "./AttackMappingDone";

/**
 * #1182: Gene's 2026-10-15 test-run item 14. The "Updated N fields across M
 * techniques" line becomes "Mapping done for {tools} tools across {n} ATT&CK
 * techniques and sub-techniques". {n} is what the run COVERED (the run's
 * applied count), not what it changed. "of {total}" shows only when a batch
 * failed, and {total} is the mappable catalog count, derived, never typed
 * (advisor, #736 comment 6216024281). Expected strings are literals.
 */

function tech(id: string, parent: string | null = null): CatalogTechnique {
  return {
    id,
    name: id,
    tactics: [],
    parent_id: parent,
    is_sub_technique: parent !== null,
  };
}

// Five techniques; T1 has two sub-techniques, so it is a computed parent and
// not mappable: four can be mapped.
const CATALOG = [
  tech("T1"),
  tech("T1.001", "T1"),
  tech("T1.002", "T1"),
  tech("T2"),
  tech("T3"),
];

function line(props: Partial<Parameters<typeof AttackMappingDone>[0]>) {
  render(
    <AttackMappingDone
      toolsAvailable={3}
      techniquesMapped={2}
      batchesFailed={0}
      catalog={CATALOG}
      {...props}
    />,
  );
  return screen.getByTestId("attack-mapping-done").textContent ?? "";
}

describe("AttackMappingDone (#1182)", () => {
  it("states the tools and the techniques the run covered", () => {
    expect(line({})).toBe(
      "Mapping done for 3 tools across 2 ATT&CK techniques and sub-techniques.",
    );
  });

  it("says of how many when a batch failed, from the mappable catalog", () => {
    expect(line({ batchesFailed: 1 })).toBe(
      "Mapping done for 3 tools across 2 of 4 ATT&CK techniques and sub-techniques.",
    );
  });

  it("is worded for zero", () => {
    expect(line({ techniquesMapped: 0, batchesFailed: 2 })).toBe(
      "Mapping done for 3 tools across 0 of 4 ATT&CK techniques and sub-techniques.",
    );
  });

  it("comma-formats the counts", () => {
    expect(
      line({ toolsAvailable: 1200, techniquesMapped: 1001, batchesFailed: 0 }),
    ).toBe(
      "Mapping done for 1,200 tools across 1,001 ATT&CK techniques and sub-techniques.",
    );
  });

  it("says nothing on a partial run until the catalog can give the total", () => {
    // Without the total the line would read as a complete run.
    render(
      <AttackMappingDone
        toolsAvailable={3}
        techniquesMapped={2}
        batchesFailed={1}
        catalog={null}
      />,
    );
    expect(screen.queryByTestId("attack-mapping-done")).toBeNull();
  });
});
