import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfGapAction } from "@/lib/csf/types";

import { CsfGapActionEditor } from "./CsfGapActionEditor";

/** #1031 (#736 6116519635): a POA&M entry on a code that is not (or no
 * longer) a gap is listed, and says so. Copy approved verbatim. */
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchGapActions: vi.fn(),
  upsertGapAction: vi.fn(),
}));

const fetchGapActions = vi.mocked(csfClient.fetchGapActions);

function action(code: string, over: Partial<CsfGapAction>): CsfGapAction {
  return {
    subcategory_code: code,
    name: `${code} outcome`,
    function: "GV",
    enterprise_level: 3,
    target_level: 4,
    default_priority: "P2",
    characterization: null,
    priority_override: null,
    owner: null,
    deadline: null,
    resources: null,
    success_criteria: null,
    poam_ref: null,
    effective_priority: "P2",
    no_longer_gap: false,
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchGapActions.mockResolvedValue({
    assessment_id: "a-1",
    actions: [
      action("GV.OC-01", {}),
      action("GV.OC-02", {
        no_longer_gap: true,
        owner: "Ops lead",
        target_level: 3,
        default_priority: null,
        effective_priority: null,
      }),
    ],
  });
});

describe("CsfGapActionEditor, an entry kept for the record (#1031)", () => {
  it("lists it with the kept line, and only on that entry", async () => {
    render(<CsfGapActionEditor serviceId="svc-1" />);
    const kept = await screen.findByTestId("gap-action-GV.OC-02");
    expect(kept).toHaveTextContent("No longer a gap: kept for the record");
    expect(screen.getByTestId("gap-action-GV.OC-01")).not.toHaveTextContent(
      "No longer a gap",
    );
    expect(screen.getAllByTestId("gap-action-kept")).toHaveLength(1);
  });
});
