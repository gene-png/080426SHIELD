import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AiStatus } from "@/lib/admin/client";

import { AiStatusBanner } from "./AiStatusBanner";

/**
 * #472: the banner renders on every admin page, and its "Load an API key" link
 * is a promise that loading one helps. It does only where a key can be loaded
 * here (`can_configure`) AND the call is offline -- for a missing SDK or a
 * placeholder model ("broken") no key fixes anything. The guard's twin is
 * pinned over its whole table; this pins the banner over the same matrix
 * (round 5 on #513: it had no test at all).
 */

let current: AiStatus | null = null;
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({ status: current }),
}));

function status(over: Partial<AiStatus>): AiStatus {
  return {
    mode: "fixture",
    provider: "anthropic",
    model: "claude-opus-5",
    ready: false,
    detail: "No API key is loaded",
    can_configure: true,
    key_source: "none",
    serves: "offline",
    ...over,
  };
}

const MATRIX: ReadonlyArray<{
  label: string;
  over: Partial<AiStatus>;
  offered: boolean;
}> = [
  { label: "offline, key loadable here", over: {}, offered: true },
  {
    label: "offline, key not loadable here",
    over: { provider: "openai", can_configure: false },
    offered: false,
  },
  {
    label: "broken, key loadable here (a placeholder model)",
    over: { serves: "broken", key_source: "database" },
    offered: false,
  },
  {
    label: "broken, key not loadable here",
    over: { serves: "broken", provider: "vertex", can_configure: false },
    offered: false,
  },
];

describe("AiStatusBanner's Load an API key link", () => {
  it("covers both answers, or the matrix proves one half only", () => {
    expect(new Set(MATRIX.map((m) => m.offered))).toEqual(
      new Set([true, false]),
    );
  });

  for (const row of MATRIX) {
    it(`${row.offered ? "offers" : "withholds"} it: ${row.label}`, () => {
      current = status(row.over);
      render(<AiStatusBanner />);
      expect(screen.getByRole("status")).toBeInTheDocument();
      const link = screen.queryByRole("link", { name: "Load an API key" });
      expect(link !== null).toBe(row.offered);
    });
  }

  it("renders nothing when AI is live", () => {
    current = status({ ready: true, serves: "live", key_source: "database" });
    const { container } = render(<AiStatusBanner />);
    expect(container).toBeEmptyDOMElement();
  });
});
