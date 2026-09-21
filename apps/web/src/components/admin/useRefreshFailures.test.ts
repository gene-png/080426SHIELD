import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useRefreshFailures } from "@/components/admin/useRefreshFailures";

/**
 * The sequencing guard, tested where it lives (#292).
 *
 * It used to live at ONE call site -- `TechDebtWorkspace.refreshOverlap` --
 * because that is where the review reported it. Three workspaces captured no
 * sequence at all, and Tech Debt's own deliverable branch sat outside its own
 * guard. A rule applied at four sites diverges at four sites, so it moved into
 * the hook and there is no unsequenced way to write any more.
 *
 * These tests are the reason that move is safe to rely on.
 */
describe("useRefreshFailures sequencing", () => {
  it("lets the newest attempt record a failure", () => {
    const { result } = renderHook(() => useRefreshFailures());
    act(() => {
      result.current.begin("score-gap").note("stale");
    });
    expect(result.current.messages).toEqual(["stale"]);
  });

  it("IGNORES a superseded attempt's failure", () => {
    // The defect, exactly: two edits ~200ms apart. #2 succeeds, so the figures
    // on screen are current; #1 then rejects. An unguarded write pins a
    // permanent "may be out of date" over figures that are up to date.
    const { result } = renderHook(() => useRefreshFailures());
    let first!: ReturnType<typeof result.current.begin>;
    act(() => {
      first = result.current.begin("score-gap");
      result.current.begin("score-gap").clear();
    });
    act(() => {
      first.note("stale");
    });
    expect(first.superseded()).toBe(true);
    expect(result.current.messages).toEqual([]);
  });

  it("IGNORES a superseded attempt's success", () => {
    // The mirror, and it is equally live: a stale SUCCESS clearing a current
    // failure would hide a real one. Testing only the failure direction would
    // pin half a guard.
    const { result } = renderHook(() => useRefreshFailures());
    let stale!: ReturnType<typeof result.current.begin>;
    act(() => {
      stale = result.current.begin("score-gap");
      result.current.begin("score-gap").note("current failure");
    });
    act(() => {
      stale.clear();
    });
    expect(result.current.messages).toEqual(["current failure"]);
  });

  it("sequences each source independently", () => {
    // A second source beginning must not supersede the first -- that would be
    // the single-slot clobbering defect reintroduced through the guard.
    const { result } = renderHook(() => useRefreshFailures());
    let interview!: ReturnType<typeof result.current.begin>;
    act(() => {
      interview = result.current.begin("interview");
      result.current.begin("score-gap").note("score stale");
    });
    act(() => {
      interview.note("prompts missing");
    });
    expect(result.current.messages.sort()).toEqual([
      "prompts missing",
      "score stale",
    ]);
  });
});
