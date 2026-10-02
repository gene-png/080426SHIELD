import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AiRun, AiRunStarted, AiRunSummary } from "./types";
import { useAiRun } from "./useAiRun";

type Result = { applied: number };

function run(over: Partial<AiRun<Result>> = {}): AiRun<Result> {
  return {
    id: "run-1",
    service_id: "svc-1",
    subject_id: "assess-1",
    purpose: "mitre_map",
    status: "running",
    serves: "offline",
    started_at: "2026-10-01T12:00:00Z",
    deadline_at: "2026-10-01T12:45:00Z",
    lock_until: "2099-01-01T00:00:00Z",
    finished_at: null,
    batches_total: null,
    batches_failed: null,
    applied_count: null,
    result: null,
    error_reason: null,
    error_message: null,
    charged_likely: null,
    ...over,
  };
}

function summary(
  over: Partial<AiRunSummary<Result>> = {},
): AiRunSummary<Result> {
  return { running: null, latest: null, last_completed: null, ...over };
}

const STARTED: AiRunStarted = {
  run_id: "run-1",
  status: "running",
  serves: "offline",
  deadline_at: "2026-10-01T12:45:00Z",
  lock_until: "2099-01-01T00:00:00Z",
  joined: false,
};

afterEach(() => {
  vi.useRealTimers();
});

describe("useAiRun (#645)", () => {
  it("follows a run it started until it completes, then reports it as the last completed", async () => {
    const fetchSummary = vi.fn().mockResolvedValue(summary());
    const fetchRun = vi
      .fn()
      .mockResolvedValueOnce(run())
      .mockResolvedValueOnce(
        run({ status: "completed", result: { applied: 3 } }),
      );
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        fetchSummary,
        fetchRun,
        pollMs: 1,
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    let finished: AiRun<Result> | undefined;
    await act(async () => {
      finished = await result.current.follow(STARTED);
    });

    expect(finished?.status).toBe("completed");
    expect(fetchRun).toHaveBeenCalledTimes(2);
    expect(result.current.running).toBeNull();
    expect(result.current.lastCompleted?.result).toEqual({ applied: 3 });
  });

  it("says it could not check when a poll fails, never that the run failed", async () => {
    const fetchSummary = vi.fn().mockResolvedValue(summary());
    const second = deferredRun();
    const fetchRun = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        fetchSummary,
        fetchRun,
        pollMs: 1,
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));

    let done: Promise<AiRun<Result>> | undefined;
    act(() => {
      done = result.current.follow(STARTED);
    });
    await waitFor(() => expect(result.current.checkFailed).toBe(true));
    // Still running, as far as anyone knows: the lock stays and nothing failed.
    expect(result.current.running?.id).toBe("run-1");
    expect(result.current.latest).toBeNull();

    await act(async () => {
      second.resolve(run({ status: "completed", result: { applied: 1 } }));
      await done;
    });
    expect(result.current.checkFailed).toBe(false);
    expect(result.current.lastCompleted?.id).toBe("run-1");
  });

  it("finds a run in progress on load, polls it, and tells the page when it ends", async () => {
    const fetchSummary = vi
      .fn()
      .mockResolvedValue(summary({ running: run(), latest: run() }));
    const fetchRun = vi
      .fn()
      .mockResolvedValueOnce(
        run({ status: "completed", result: { applied: 2 } }),
      );
    const onFinished = vi.fn();
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        fetchSummary,
        fetchRun,
        onFinished,
        pollMs: 1,
      }),
    );
    await waitFor(() => expect(onFinished).toHaveBeenCalledTimes(1));
    expect(onFinished.mock.calls[0][0].status).toBe("completed");
    expect(result.current.running).toBeNull();
  });

  it("keeps the last completed run when a later one fails (#271)", async () => {
    const earlier = run({
      id: "run-0",
      status: "completed",
      result: { applied: 5 },
    });
    const fetchSummary = vi
      .fn()
      .mockResolvedValue(summary({ latest: earlier, last_completed: earlier }));
    const fetchRun = vi
      .fn()
      .mockResolvedValueOnce(
        run({ status: "failed", error_reason: "ai_call_failed" }),
      );
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        fetchSummary,
        fetchRun,
        pollMs: 1,
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(async () => {
      await result.current.follow(STARTED);
    });
    expect(result.current.latest?.status).toBe("failed");
    expect(result.current.lastCompleted?.id).toBe("run-0");
  });

  it("reports a summary it could not read as an error, not as 'no run'", async () => {
    // An internal string ("ATT&CK proxy 502") is never shown to anyone.
    const fetchSummary = vi
      .fn()
      .mockRejectedValue(new Error("ATT&CK proxy 502"));
    const { result } = renderHook(() =>
      useAiRun<Result>({ serviceId: "svc-1", fetchSummary, fetchRun: vi.fn() }),
    );
    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.running).toBeNull();
    expect(result.current.loadError).toBe("the server could not be reached");
  });
});

function deferredRun(): {
  promise: Promise<AiRun<Result>>;
  resolve: (r: AiRun<Result>) => void;
} {
  let resolve!: (r: AiRun<Result>) => void;
  const promise = new Promise<AiRun<Result>>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function refusal(status: number, message: string): Error {
  return Object.assign(new Error(`proxy ${status}`), {
    status,
    payload: { error: { code: status, reason: "forbidden", message } },
  });
}

describe("useAiRun, review round 1 (#645)", () => {
  it("W4: an ANSWERED refusal stops polling and shows the api's message", async () => {
    const fetchSummary = vi.fn().mockResolvedValue(summary());
    const fetchRun = vi
      .fn()
      .mockRejectedValue(
        refusal(403, "You no longer have access to this service."),
      );
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        fetchSummary,
        fetchRun,
        pollMs: 1,
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    let ended: AiRun<Result> | undefined;
    await act(async () => {
      ended = await result.current.follow(STARTED);
    });
    expect(result.current.pollRefused).toBe(
      "You no longer have access to this service.",
    );
    expect(result.current.checkFailed).toBe(false);
    expect(ended?.status).toBe("running"); // not completed: the caller re-reads nothing
    const calls = fetchRun.mock.calls.length;
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchRun.mock.calls.length).toBe(calls);
  });

  it("W4: past lock_until with no answer, polling stops and says so -- never 'failed'", async () => {
    const fetchSummary = vi.fn().mockResolvedValue(summary());
    const fetchRun = vi
      .fn()
      .mockRejectedValue(new TypeError("Failed to fetch"));
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        fetchSummary,
        fetchRun,
        pollMs: 1,
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(async () => {
      await result.current.follow({
        ...STARTED,
        lock_until: "2000-01-01T00:00:00Z",
      });
    });
    expect(result.current.pastLockUntil).toBe(true);
    expect(result.current.latest).toBeNull();
    const calls = fetchRun.mock.calls.length;
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchRun.mock.calls.length).toBe(calls);
  });

  it("W3: a new service never shows the old service's run, and the old poll stops", async () => {
    const held = deferredRun();
    const fetchSummary = vi.fn((serviceId: string) =>
      Promise.resolve(
        serviceId === "svc-A"
          ? summary({ running: run({ id: "run-A", service_id: "svc-A" }) })
          : summary(),
      ),
    );
    const fetchRun = vi.fn().mockReturnValueOnce(held.promise);
    const { result, rerender } = renderHook(
      ({ serviceId }) =>
        useAiRun<Result>({ serviceId, fetchSummary, fetchRun, pollMs: 1 }),
      { initialProps: { serviceId: "svc-A" } },
    );
    await waitFor(() => expect(result.current.running?.id).toBe("run-A"));
    rerender({ serviceId: "svc-B" });
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(result.current.running).toBeNull();
    await act(async () => {
      held.resolve(run({ id: "run-A", service_id: "svc-A" }));
      await held.promise;
    });
    expect(result.current.running).toBeNull();
    const calls = fetchRun.mock.calls.length;
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchRun.mock.calls.length).toBe(calls);
  });

  it("W1: a past run on another subject never describes this one", async () => {
    const other = run({
      id: "run-0",
      status: "completed",
      subject_id: "assess-0",
      result: { applied: 1 },
    });
    const fetchSummary = vi
      .fn()
      .mockResolvedValue(summary({ latest: other, last_completed: other }));
    const { result } = renderHook(() =>
      useAiRun<Result>({
        serviceId: "svc-1",
        subjectId: "assess-1",
        fetchSummary,
        fetchRun: vi.fn(),
      }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    expect(fetchSummary).toHaveBeenCalledWith("svc-1", "assess-1");
    expect(result.current.lastCompleted).toBeNull();
    expect(result.current.latest).toBeNull();
  });

  it("reconcile: an ANSWERED refusal is shown, not swallowed", async () => {
    const fetchSummary = vi
      .fn()
      .mockResolvedValueOnce(summary())
      .mockRejectedValueOnce(refusal(404, "Service not found."));
    const { result } = renderHook(() =>
      useAiRun<Result>({ serviceId: "svc-1", fetchSummary, fetchRun: vi.fn() }),
    );
    await waitFor(() => expect(result.current.phase).toBe("ready"));
    await act(async () => {
      await result.current.reconcile();
    });
    expect(result.current.pollRefused).toBe("Service not found.");
  });
});
