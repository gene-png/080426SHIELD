"use client";

import * as React from "react";

import { clientFacingError } from "@/lib/describe-save-error";

import type { AiRun, AiRunStarted, AiRunSummary } from "./types";

/** How often a running run is polled. A full ATT&CK run takes minutes. */
export const AI_RUN_POLL_MS = 3000;

export interface UseAiRun<R> {
  /** Whether the service's runs have been read yet. */
  phase: "loading" | "ready" | "error";
  loadError: string | null;
  /** The run holding this service's edit lock, as last read. */
  running: AiRun<R> | null;
  /** The newest run, whatever it ended as. */
  latest: AiRun<R> | null;
  /** The newest COMPLETED run: the one whose results stand (#271). */
  lastCompleted: AiRun<R> | null;
  /**
   * The newest poll could not reach the api. The run may well still be
   * running, so this is NEVER reported as the run failing: "could not check"
   * and "failed" are different facts, and only the api knows the second.
   */
  checkFailed: boolean;
  /** Follow a run this page started. Resolves once it finishes, either way. */
  follow: (started: AiRunStarted) => Promise<AiRun<R>>;
  /**
   * After a Run-AI POST whose outcome is unknown (#550): read the service's
   * runs ONCE, and if one is in progress, show and follow it. A read that
   * fails changes nothing -- the page already says the outcome is unknown,
   * and a second message would contradict it.
   */
  reconcile: () => Promise<void>;
}

interface State<R> {
  serviceId: string;
  phase: "loading" | "ready" | "error";
  loadError: string | null;
  running: AiRun<R> | null;
  latest: AiRun<R> | null;
  lastCompleted: AiRun<R> | null;
  checkFailed: boolean;
}

function initial<R>(serviceId: string): State<R> {
  return {
    serviceId,
    phase: "loading",
    loadError: null,
    running: null,
    latest: null,
    lastCompleted: null,
    checkFailed: false,
  };
}

function placeholder<R>(serviceId: string, started: AiRunStarted): AiRun<R> {
  // What the 202 says about the run, until the first poll says more.
  return {
    id: started.run_id,
    service_id: serviceId,
    purpose: "",
    status: "running",
    serves: started.serves,
    started_at: "",
    deadline_at: started.deadline_at,
    finished_at: null,
    batches_total: null,
    batches_failed: null,
    applied_count: null,
    result: null,
    error_reason: null,
    error_message: null,
    charged_likely: null,
  };
}

/**
 * Read a service's Run-AI runs and follow the one in progress (#645).
 *
 * On load it reads the service's runs, so a reload mid-run finds the run,
 * shows the lock and keeps polling; `onFinished` then tells the page a run it
 * did not start has ended. A run the page starts is followed with `follow`,
 * whose promise resolves on the run's terminal state instead.
 *
 * The fetchers are passed in so each service's client module owns its own
 * requests and its tests can mock them.
 */
export function useAiRun<R>({
  serviceId,
  fetchSummary,
  fetchRun,
  onFinished,
  pollMs = AI_RUN_POLL_MS,
}: {
  serviceId: string;
  fetchSummary: (serviceId: string) => Promise<AiRunSummary<R>>;
  fetchRun: (runId: string) => Promise<AiRun<R>>;
  onFinished?: (run: AiRun<R>) => void;
  pollMs?: number;
}): UseAiRun<R> {
  const [state, setState] = React.useState<State<R>>(() => initial(serviceId));
  // Latest callbacks, so a re-render with new inline functions does not
  // restart polling.
  const fetchers = React.useRef({ fetchSummary, fetchRun, onFinished });
  // Declared before the load effect, so it runs first and the load reads the
  // current fetchers.
  React.useEffect(() => {
    fetchers.current = { fetchSummary, fetchRun, onFinished };
  });
  const alive = React.useRef(true);
  const polling = React.useRef(new Set<string>());
  const timers = React.useRef(new Set<ReturnType<typeof setTimeout>>());
  const followers = React.useRef(new Map<string, (run: AiRun<R>) => void>());

  const later = React.useCallback(
    (fn: () => void) => {
      const t = setTimeout(() => {
        timers.current.delete(t);
        fn();
      }, pollMs);
      timers.current.add(t);
    },
    [pollMs],
  );

  const poll = React.useCallback(
    (runId: string) => {
      if (polling.current.has(runId)) return;
      polling.current.add(runId);
      const tick = async (): Promise<void> => {
        if (!alive.current) return;
        let run: AiRun<R>;
        try {
          run = await fetchers.current.fetchRun(runId);
        } catch {
          // Could not LOOK. Say so and look again; the run is not failed.
          if (!alive.current) return;
          setState((s) => ({ ...s, checkFailed: true }));
          later(() => void tick());
          return;
        }
        if (!alive.current) return;
        if (run.status === "running") {
          setState((s) => ({ ...s, checkFailed: false, running: run }));
          later(() => void tick());
          return;
        }
        polling.current.delete(runId);
        setState((s) => ({
          ...s,
          checkFailed: false,
          running: s.running?.id === run.id ? null : s.running,
          latest: run,
          lastCompleted: run.status === "completed" ? run : s.lastCompleted,
        }));
        const follower = followers.current.get(runId);
        if (follower) {
          followers.current.delete(runId);
          follower(run);
        } else {
          fetchers.current.onFinished?.(run);
        }
      };
      void tick();
    },
    [later],
  );

  React.useEffect(() => {
    alive.current = true;
    const pollingNow = polling.current;
    const timersNow = timers.current;
    fetchers.current
      .fetchSummary(serviceId)
      .then((summary) => {
        if (!alive.current) return;
        setState({
          serviceId,
          phase: "ready",
          loadError: null,
          running: summary.running,
          latest: summary.latest,
          lastCompleted: summary.last_completed,
          checkFailed: false,
        });
        if (summary.running) poll(summary.running.id);
      })
      .catch((err: unknown) => {
        if (!alive.current) return;
        setState({
          ...initial<R>(serviceId),
          phase: "error",
          loadError: clientFacingError(err, "the server could not be reached"),
        });
      });
    return () => {
      alive.current = false;
      for (const t of timersNow) clearTimeout(t);
      timersNow.clear();
      pollingNow.clear();
    };
  }, [serviceId, poll]);

  const follow = React.useCallback(
    (started: AiRunStarted): Promise<AiRun<R>> => {
      const promise = new Promise<AiRun<R>>((resolve) => {
        followers.current.set(started.run_id, resolve);
      });
      setState((s) => ({
        ...s,
        running:
          s.running?.id === started.run_id
            ? s.running
            : placeholder<R>(serviceId, started),
      }));
      poll(started.run_id);
      return promise;
    },
    [poll, serviceId],
  );

  // Derived, not reset: a render for a new service never shows the old one's
  // runs, even before the effect above has run.
  const current = state.serviceId === serviceId ? state : initial<R>(serviceId);
  const reconcile = React.useCallback(async (): Promise<void> => {
    let summary: AiRunSummary<R>;
    try {
      summary = await fetchers.current.fetchSummary(serviceId);
    } catch (err) {
      console.warn(
        `[useAiRun] could not re-read runs after an unknown outcome: ${String(err)}`,
      );
      return;
    }
    if (!alive.current) return;
    setState({
      serviceId,
      phase: "ready",
      loadError: null,
      running: summary.running,
      latest: summary.latest,
      lastCompleted: summary.last_completed,
      checkFailed: false,
    });
    if (summary.running) poll(summary.running.id);
  }, [poll, serviceId]);

  return { ...current, follow, reconcile };
}
