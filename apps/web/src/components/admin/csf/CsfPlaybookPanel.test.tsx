import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { EnterpriseProfile } from "@/lib/csf/types";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

// Deterministic + offline: the lib client is mocked, and the child editors /
// preview button are stubbed so this test isolates CsfPlaybookPanel's own
// enterprise-profile fetch and its reqSeq stale-fetch guard.
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

const fetchEnterpriseProfile = vi.mocked(csfClient.fetchEnterpriseProfile);
const seedProfiles = vi.mocked(csfClient.seedProfiles);

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (err: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function ent(code: string): EnterpriseProfile {
  return {
    tiers_in_use: ["moderate"],
    subcategories: [
      {
        subcategory_code: code,
        name: `${code} outcome`,
        function: "GV",
        tier_levels: { moderate: 2 },
        enterprise_level: 2,
        rollup_rule: 1,
        target_level: 3,
        gap: false,
        priority: null,
      },
    ],
  };
}

describe("CsfPlaybookPanel reqSeq stale-fetch guard", () => {
  it("discards a stale mount fetch that resolves after a newer reload", async () => {
    const first = deferred<EnterpriseProfile>(); // mount fetch (seq 1) — slow
    const second = deferred<EnterpriseProfile>(); // post-seed reload (seq 2)
    fetchEnterpriseProfile
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    seedProfiles.mockResolvedValue(["moderate"]);

    render(<CsfPlaybookPanel serviceId="svc-1" />);

    // Mount fetch is in-flight (enterprise still null => not seeded), so the
    // Seed button is offered. Clicking it triggers the second fetch (seq 2).
    fireEvent.click(
      await screen.findByRole("button", { name: "Seed Working Profiles" }),
    );
    await act(async () => {
      // seedProfiles resolves, then reload() issues the seq-2 fetch.
      await Promise.resolve();
    });
    expect(fetchEnterpriseProfile).toHaveBeenCalledTimes(2);

    // Newer request (seq 2) resolves first with the fresh data.
    await act(async () => {
      second.resolve(ent("FRESH.1"));
    });

    // The slow mount fetch (seq 1) resolves LATE with stale data. The guard must
    // discard it; without the guard it would overwrite the fresh enterprise.
    await act(async () => {
      first.resolve(ent("STALE.1"));
    });

    expect(await screen.findByText("FRESH.1 outcome")).toBeInTheDocument();
    expect(screen.queryByText("STALE.1 outcome")).not.toBeInTheDocument();
  });

  it("surfaces a failed initial load to the error state (fail loudly)", async () => {
    fetchEnterpriseProfile.mockRejectedValue(new Error("boom-profile"));

    render(<CsfPlaybookPanel serviceId="svc-err" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom-profile");
  });
});
