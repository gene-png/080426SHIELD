import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { EnterpriseProfile } from "@/lib/csf/types";

import type * as React from "react";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/**
 * #852 on the consultant's screen. A Working Profile row kept on ID.AM-09 (a
 * subcategory NIST CSF 2.0 does not have) is not rolled up and not in the
 * table, and the API sends the approved sentence saying so. Rendered as given.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  exportPlaybook: vi.fn(),
  fetchCsfRun: vi.fn(),
  fetchCsfRunSummary: vi.fn(() =>
    Promise.resolve({ running: null, latest: null, last_completed: null }),
  ),
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

const S2 =
  "1 recorded Working Profile row belongs to ID.AM-09, a subcategory NIST CSF" +
  " 2.0 does not have, so it is not scored or rolled up. 1 action plan" +
  " recorded for it is kept and not listed.";

const ROW = {
  subcategory_code: "GV.OC-01",
  name: "Mission understanding",
  function: "GV",
  tier_levels: { high: 2 },
  enterprise_level: 2,
  rollup_rule: 1,
  target_level: null,
  gap: false,
  priority: null,
};

function profile(over: Partial<EnterpriseProfile>): EnterpriseProfile {
  return {
    tiers_in_use: ["high"],
    subcategories: [ROW],
    ...over,
  } as EnterpriseProfile;
}

describe("CsfPlaybookPanel states a Working Profile row kept on a retired subcategory (#852)", () => {
  it("renders the API's sentence", async () => {
    vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue(
      profile({ retired_rows: 1, retired_rows_note: S2 }),
    );
    render(<CsfPlaybookPanel serviceId="svc-852" />);
    expect(await screen.findByTestId("csf-retired-rows")).toHaveTextContent(S2);
  });

  // The action-only sentence, approved with commas (#736 comment 6056012075).
  // Its row count is 0: the note, not the count, decides whether it shows.
  it.each([
    [
      "one plan",
      "1 action plan recorded for ID.AM-09, a subcategory NIST CSF 2.0 does" +
        " not have, is kept and not listed.",
    ],
    [
      // Not reachable today (one plan per assessment and code, and one
      // retired code); the API's plural form, rendered as given.
      "several plans",
      "2 action plans recorded for ID.AM-09, a subcategory NIST CSF 2.0 does" +
        " not have, are kept and not listed.",
    ],
  ])("renders the action-only sentence, %s", async (_label, note) => {
    vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue(
      profile({ retired_rows: 0, retired_rows_note: note }),
    );
    render(<CsfPlaybookPanel serviceId="svc-852" />);
    expect(await screen.findByTestId("csf-retired-rows")).toHaveTextContent(
      note,
    );
  });

  it("says nothing when nothing was kept", async () => {
    vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue(
      profile({ retired_rows: 0, retired_rows_note: null }),
    );
    render(<CsfPlaybookPanel serviceId="svc-852" />);
    expect(await screen.findByText(/tier\(s\) in use/)).toBeVisible();
    expect(screen.queryByTestId("csf-retired-rows")).toBeNull();
  });
});
