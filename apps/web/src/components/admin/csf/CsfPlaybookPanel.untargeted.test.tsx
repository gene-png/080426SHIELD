import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { EnterpriseProfile } from "@/lib/csf/types";

import type * as React from "react";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/**
 * #762 on the consultant's screen. The panel counted "N subcategories with a
 * gap" over rows that have a target, and said nothing about the rows that
 * have none, which is every row after seed + Run AI. Rendered: the count line
 * is read off the page.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  exportPlaybook: vi.fn(),
}));
vi.mock("../AiPreviewButton", () => ({ AiPreviewButton: () => null }));
vi.mock("./CsfDimensionEditor", () => ({ CsfDimensionEditor: () => null }));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
vi.mock("../RunAiGuard", () => ({
  RunAiGuard: ({
    children,
  }: {
    children: (props: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: () => undefined }),
}));

function sub(code: string, gap: boolean, target: number | null) {
  return {
    subcategory_code: code,
    name: `${code} outcome`,
    function: "GV",
    tier_levels: { moderate: 2 },
    enterprise_level: 2,
    rollup_rule: 1,
    target_level: target,
    gap,
    priority: gap ? "P2" : null,
  };
}

async function countLine(subcategories: ReturnType<typeof sub>[]) {
  vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue({
    tiers_in_use: ["moderate"],
    subcategories,
  } as EnterpriseProfile);
  render(<CsfPlaybookPanel serviceId="svc-762" />);
  const line = await screen.findByText(/tier\(s\) in use/);
  return (line.textContent ?? "").replace(/\s+/g, " ").trim();
}

describe("CsfPlaybookPanel counts the subcategories with no target (#762)", () => {
  it("states them beside the gap count", async () => {
    expect(
      await countLine([
        sub("GV.OC-01", true, 4),
        sub("GV.OC-02", false, 2),
        sub("GV.OC-03", false, null),
        sub("GV.OC-04", false, null),
      ]),
    ).toBe("1 tier(s) in use · 1 subcategory with a gap · 2 with no target");
  });

  it("says nothing extra when every subcategory has a target", async () => {
    expect(
      await countLine([sub("GV.OC-01", true, 4), sub("GV.OC-02", false, 2)]),
    ).toBe("1 tier(s) in use · 1 subcategory with a gap");
  });
});
