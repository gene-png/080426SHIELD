import { describe, expect, it } from "vitest";

import { SECTIONS } from "@/components/service-shell/SectionBar";
import { omittedSections } from "@/components/service-shell/frameRoutes";

import {
  CSF_BLOCK_SECTIONS,
  CSF_NEEDS_ASSESSMENT,
  CSF_SECTION_COPY,
  showsCsfBlock,
  type CsfBlock,
} from "./csfSections";

const BLOCKS = Object.keys(CSF_BLOCK_SECTIONS) as CsfBlock[];
const CSF_SECTIONS = SECTIONS.map((s) => s.key).filter(
  (k) => !omittedSections("nist_csf").includes(k),
);

describe("the CSF block-to-section table (#1378)", () => {
  it("places every block in at least one section", () => {
    for (const block of BLOCKS) {
      expect(CSF_BLOCK_SECTIONS[block].length, block).toBeGreaterThan(0);
    }
  });

  it("only names sections a CSF service has (Inputs is folded into AI draft)", () => {
    for (const block of BLOCKS) {
      for (const section of CSF_BLOCK_SECTIONS[block]) {
        expect(CSF_SECTIONS, `${block} -> ${section}`).toContain(section);
      }
    }
  });

  it("places each block in exactly the sections listed in the issue's map", () => {
    // Written from the component map on issue #1378 (the plan comment), not
    // from the table under test.
    const expected: Record<string, string[]> = {
      revisionBanner: ["overview"],
      progressStages: ["overview"],
      discardDraft: ["overview"],
      startAssessment: ["overview"],
      startRevision: ["approve-and-release"],
      aiSource: ["ai-draft"],
      playbookRun: ["ai-draft"],
      questionnaire: ["ai-draft"],
      playbookTable: ["review"],
      dimensionEditor: ["review"],
      approve: ["review"],
      gapActions: ["analysis"],
      gapList: ["analysis"],
      staleDocs: ["generate"],
      deliverable: ["generate"],
      scoreCard: ["overview"],
      messages: ["overview"],
    };
    for (const [block, sections] of Object.entries(expected)) {
      expect([...CSF_BLOCK_SECTIONS[block as CsfBlock]], block).toEqual(
        sections,
      );
    }
  });

  it("shows the status and read failures in every CSF section", () => {
    for (const section of CSF_SECTIONS) {
      expect(showsCsfBlock(section, "status"), section).toBe(true);
      expect(showsCsfBlock(section, "readFailures"), section).toBe(true);
    }
  });

  it("is the whole page when there is no section", () => {
    for (const block of BLOCKS)
      expect(showsCsfBlock(undefined, block)).toBe(true);
  });

  it("every section that needs an assessment is a CSF section", () => {
    for (const section of CSF_NEEDS_ASSESSMENT) {
      expect(CSF_SECTIONS).toContain(section);
    }
  });

  it("has a header for every section key", () => {
    for (const s of SECTIONS) {
      expect(CSF_SECTION_COPY.header[s.key].canDo.length).toBeGreaterThan(0);
    }
  });
});
