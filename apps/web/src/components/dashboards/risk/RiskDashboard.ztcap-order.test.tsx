import "@testing-library/jest-dom/vitest";

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDashboard } from "./RiskDashboard";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

/**
 * #944, the advisor's ruling on #736 comment 6069566861, option 1: the DoD cap
 * note renders immediately after the Zero Trust target line, so #861's target
 * line and #915's note read as one baseline rather than two. No new copy, only
 * order. Both sentences are copied from their approved copy (#861's target
 * line; S3 at #736 comment 6049667540), never built from the code. The targets
 * are a CSF and a DoD Zero Trust engagement, the one shape the cap can reach.
 *
 * Adjacency is read in DOCUMENT ORDER over the rendered text, which is the
 * order a reader and a screen reader meet it: the text that follows the Zero
 * Trust target line must be the cap note.
 */

const ZT_LINE =
  "Zero Trust findings are measured against target stage 3, the engagement target when this register was generated.";
const SINGULAR =
  "In the DoD Zero Trust assessment, 1 capability has no DoD Advanced activities, so its target is Target (2): it is a finding only below Target. The Zero Trust deliverable names it.";

/** Every non-blank text node under `root`, trimmed, in document order. */
function textsInOrder(root: HTMLElement): string[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const out: string[] = [];
  for (let n = walker.nextNode(); n !== null; n = walker.nextNode()) {
    const t = (n.textContent ?? "").trim();
    if (t !== "") out.push(t);
  }
  return out;
}

function data(): RiskDashboardData {
  return {
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    client_id: "00000000-0000-0000-0000-0000000000aa",
    released_at: "2026-10-04T00:00:00Z",
    version: 1,
    total_entries: 0,
    critical_count: 0,
    high_count: 0,
    tier_counts: {},
    axis_counts: {},
    action_counts: {},
    matrix: [],
    entries: [],
    entries_without_tier: 0,
    entries_without_axis: 0,
    entries_without_action: 0,
    targets: [
      {
        kind: "csf",
        framework: null,
        target: 3,
        source: "client",
        origin: "live_at_generate",
      },
      {
        kind: "zt",
        framework: "dod_ztra",
        target: 3,
        source: "client",
        origin: "live_at_generate",
      },
    ],
    targets_recorded: true,
    zt_capped_target_note: SINGULAR,
  };
}

describe("RiskDashboard puts the DoD cap note after the Zero Trust target line (#944)", () => {
  it("renders the cap note immediately after the Zero Trust target line", () => {
    const { container } = render(<RiskDashboard data={data()} />);
    // The positive state first: both sentences are on the page, once each.
    const texts = textsInOrder(container);
    expect(texts.filter((t) => t === ZT_LINE)).toHaveLength(1);
    expect(texts.filter((t) => t === SINGULAR)).toHaveLength(1);
    // Then the order: the cap note is the very next text.
    const at = texts.indexOf(ZT_LINE);
    expect(texts.slice(at + 1, at + 2)).toEqual([SINGULAR]);
  });
});
