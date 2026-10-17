import { describe, expect, it } from "vitest";

import { SECTIONS } from "@/components/service-shell/SectionBar";
import { omittedSections } from "@/components/service-shell/frameRoutes";

import {
  ZT_BLOCK_SECTIONS,
  ZT_SECTION_COPY,
  ZT_SECTION_VISIBILITY,
  showsBlock,
  type ZtBlock,
} from "./ztSections";

// The sections a Zero Trust service has, from the frame (not from the module
// under test): the frame omits Inputs for CSF and Zero Trust.
const ZT_SECTIONS = SECTIONS.map((s) => s.key).filter(
  (k) => !omittedSections("zero_trust_cisa").includes(k),
);

// Blocks deliberately shown in more than one section, written out here so a
// new multi-section block must be added on purpose: each is a state the reader
// needs wherever they are.
const EVERYWHERE: readonly ZtBlock[] = [
  "statusPill",
  "revisionBanner",
  "readFailures",
  "catalogLoading",
];

describe("ztSections, the Zero Trust component map (#1379)", () => {
  it("has the seven client-frame sections plus Recommendations, and no Inputs", () => {
    expect(ZT_SECTIONS).toEqual([
      "overview",
      "ai-draft",
      "review",
      "analysis",
      "generate",
      "quality-check",
      "approve-and-release",
      "recommendations",
    ]);
  });

  it("puts every block in at least one section, and only in this service's sections", () => {
    for (const [block, sections] of Object.entries(ZT_BLOCK_SECTIONS)) {
      expect(sections.length, block).toBeGreaterThan(0);
      for (const s of sections) {
        expect(ZT_SECTIONS, `${block} -> ${s}`).toContain(s);
      }
    }
  });

  it("puts every block in exactly one section, except the four shown everywhere", () => {
    for (const [block, sections] of Object.entries(ZT_BLOCK_SECTIONS)) {
      if (EVERYWHERE.includes(block as ZtBlock)) {
        expect(sections.length, block).toBeGreaterThan(1);
      } else {
        expect(sections, block).toHaveLength(1);
      }
    }
  });

  it("gives every section a block of its own, so none renders only a header", () => {
    for (const section of ZT_SECTIONS) {
      const own = Object.entries(ZT_BLOCK_SECTIONS).filter(
        ([block, sections]) =>
          !EVERYWHERE.includes(block as ZtBlock) &&
          (sections as readonly string[]).includes(section),
      );
      expect(own.length, section).toBeGreaterThan(0);
    }
  });

  it("gives every section a header (purpose and one to three things to do) and a visibility", () => {
    for (const section of ZT_SECTIONS) {
      const h =
        ZT_SECTION_COPY.header[section as keyof typeof ZT_SECTION_COPY.header];
      expect(h.purpose.trim(), section).not.toBe("");
      expect(h.canDo.length, section).toBeGreaterThanOrEqual(1);
      expect(h.canDo.length, section).toBeLessThanOrEqual(3);
      expect(
        ZT_SECTION_VISIBILITY[section as keyof typeof ZT_SECTION_VISIBILITY],
        section,
      ).toBeDefined();
    }
  });

  it("shows the whole page when there is no section, and a block only in its sections otherwise", () => {
    expect(showsBlock(undefined, "runAi")).toBe(true);
    expect(showsBlock("ai-draft", "runAi")).toBe(true);
    expect(showsBlock("review", "runAi")).toBe(false);
    expect(showsBlock("review", "questionnaire")).toBe(true);
    expect(showsBlock("overview", "questionnaire")).toBe(false);
    // Zero Trust has no Inputs section, so nothing is shown there.
    expect(showsBlock("inputs", "runAi")).toBe(false);
  });

  it("makes Recommendations the only admin-only section, and 'internal' only", () => {
    expect(ZT_SECTION_VISIBILITY.recommendations).toBe("internal");
  });
});
