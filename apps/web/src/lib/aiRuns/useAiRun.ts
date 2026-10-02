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
  /** The newest run on this page's subject, whatever it ended as. */
  latest: AiRun<R> | null;
  /** The newest COMPLETED run on this page's subject: its results stand (#271). */
  lastCompleted: AiRun<R> | null;
  /**
   * The newest poll could not reach the api. The run may well still be
   * running, so this is NEVER reported as the run failing: "could not check"
   * and "failed" are different facts, and only the api knows the second.
   */
  checkFailed: boolean;
  /**
   * The api ANSWERED a poll with a refusal (401, 403, 404...): its own typed
   * message. Polling has stopped; a refusal will not change by asking again.
   */
  pollRefused: string | null;
  /**
   * Polling gave up because the run is past the latest it can hold the lock
   * (`lock_until`) and the api could not be reached to say how it ended.
   */
  pastLockUntil: boolean;
  /** Follow a run this page started. Resolves once it ends or polling stops. */
  follow: (started: AiRunStarted) => Promise<AiRun<R>>;
  /**
   * After a Run-AI POST whose outcome is unknown (#550): read the service's
   * runs ONCE, and if one is in progress, show and follow it. A read the api
   * could not answer changes nothing -- the page already says the outcome is
   * unknown -- but an ANSWERED refusal is shown, as a poll's is.
   */
  reconcile: () => Promise<void>;
}

interface State<R> {
  key: string;
  phase: "loading" | "ready" | "error";
  loadError: string | null;
  running: AiRun<R> | null;
  latest: AiRun<R> | null;
  lastCompleted: AiRun<R> | null;
  checkFailed: boolean;
  pollRefused: string | null;
  pastLockUntil: boolean;
}

function initial<R>(key: string): State<R> {
  return {
    key,
    phase: "loading",
    loadError: null,
    running: null,
    latest: null,
    lastCompleted: null,
    checkFailed: false,
    pollRefused: null,
    pastLockUntil: false,
  };
}

/**
 * An error the api ANSWERED (a 4xx with its own message), as opposed to one
 * where nothing usable came back: a network failure, or the proxy's 504
 * "outcome unknown".
 */
function answeredRefusal(err: unknown): boolean {
  const status = (err as { status?: unknown } | null)?.status;
  return typeof status === "number" && status >= 400 && status < 500;
}

function placeholder<R>(
  serviceId: string,
  subjectId: string | null | undefined,
  started: AiRunStarted,
): AiRun<R> {
  // What the 202 says about the run, until the first poll says more.
  return {
    id: started.run_id,
    service_id: serviceId,
    subject_id: subjectId ?? "",
    purpose: "",
    status: "running",
    serves: started.serves,
    started_at: "",
    deadline_at: started.deadline_at,
    lock_until: started.lock_until,
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
 * `subjectId` scopes what the page is TOLD about past runs to its own
 * assessment (#271): a string is that assessment; `null` means the page has
 * no assessment yet, so no past run describes it; `undefined` means the
 * service has no per-assessment scope (Tech Debt). The lock (`running`) is
 * always the service's.
 *
 * Every poll loop belongs to ONE generation of this hook's inputs. When the
 * service or subject changes, the old generation's ticks stop and none of
 * them can write into the new one's state (review W3).
 */
export function useAiRun<R>({
  serviceId,
  subjectId,
  fetchSummary,
  fetchRun,
  onFinished,
  pollMs = AI_RUN_POLL_MS,
}: {
  serviceId: string;
  subjectId?: string | null;
  fetchSummary: (
    serviceId: string,
    subjectId?: string,
  ) => Promise<AiRunSummary<R>>;
  fetchRun: (runId: string) => Promise<AiRun<R>>;
  onFinished?: (run: AiRun<R>) => void;
  pollMs?: number;
}): UseAiRun<R> {
  const key = `${serviceId}|${subjectId === undefined ? "*" : (subjectId ?? "-")}`;
  const [state, setState] = React.useState<State<R>>(() => initial(key));
  const fetchers = React.useRef({ fetchSummary, fetchRun, onFinished });
  // Declared before the load effect, so it runs first and the load reads the
  // current fetchers.
  React.useEffect(() => {
    fetchers.current = { fetchSummary, fetchRun, onFinished };
  });
  /** The current generation; a tick from any other one does nothing. */
  const generation = React.useRef(0);
  const timers = React.useRef(new Set<ReturnType<typeof setTimeout>>());
  const polling = React.useRef(new Set<string>());
  const followers = React.useRef(new Map<string, (run: AiRun<R>) => void>());

  /** setState, but only into the generation's own key. */
  const update = React.useCallback(
    (forKey: string, fn: (s: State<R>) => State<R>) =>
      setState((s) => (s.key === forKey ? fn(s) : s)),
    [],
  );

  const settle = React.useCallback((runId: string, run: AiRun<R>) => {
    const follower = followers.current.get(runId);
    if (follower) {
      followers.current.delete(runId);
      follower(run);
      return true;
    }
    return false;
  }, []);

  const poll = React.useCallback(
    (runId: string, gen: number, forKey: string, last: AiRun<R> | null) => {
      if (polling.current.has(runId)) return;
      polling.current.add(runId);
      let latestSeen = last;
      const later = (fn: () => void) => {
        const t = setTimeout(() => {
          timers.current.delete(t);
          fn();
        }, pollMs);
        timers.current.add(t);
      };
      const stop = () => {
        polling.current.delete(runId);
        if (latestSeen) settle(runId, latestSeen);
      };
      const tick = async (): Promise<void> => {
        if (generation.current !== gen) return stop();
        let run: AiRun<R>;
        try {
          run = await fetchers.current.fetchRun(runId);
        } catch (err) {
          if (generation.current !== gen) return stop();
          if (answeredRefusal(err)) {
            // The api answered: say what it said, and stop asking.
            update(forKey, (s) => ({
              ...s,
              checkFailed: false,
              pollRefused: clientFacingError(err, "The run could not be read."),
            }));
            return stop();
          }
          const until = latestSeen?.lock_until;
          if (until && Date.now() > Date.parse(until)) {
            // Past the latest the run could hold the lock, and still no
            // answer: stop rather than poll forever. Not "failed".
            update(forKey, (s) => ({
              ...s,
              checkFailed: false,
              pastLockUntil: true,
            }));
            return stop();
          }
          // Could not LOOK. Say so and look again; the run is not failed.
          update(forKey, (s) => ({ ...s, checkFailed: true }));
          later(() => void tick());
          return;
        }
        if (generation.current !== gen) return stop();
        latestSeen = run;
        if (run.status === "running") {
          update(forKey, (s) => ({ ...s, checkFailed: false, running: run }));
          later(() => void tick());
          return;
        }
        polling.current.delete(runId);
        update(forKey, (s) => {
          const ours = scopedTo(run, s.key);
          return {
            ...s,
            checkFailed: false,
            running: s.running?.id === run.id ? null : s.running,
            latest: ours ? run : s.latest,
            lastCompleted:
              ours && run.status === "completed" ? run : s.lastCompleted,
          };
        });
        if (!settle(runId, run)) fetchers.current.onFinished?.(run);
      };
      void tick();
    },
    [pollMs, settle, update],
  );

  React.useEffect(() => {
    const gen = ++generation.current;
    const timersNow = timers.current;
    const pollingNow = polling.current;
    const cleanup = () => {
      // This generation is over: its ticks see a newer one and stop.
      for (const t of timersNow) clearTimeout(t);
      timersNow.clear();
      pollingNow.clear();
    };
    // No assessment yet: a run needs one, so there is nothing to read.
    if (subjectId === null) return cleanup;
    fetchers.current
      .fetchSummary(serviceId, subjectId ?? undefined)
      .then((summary) => {
        if (generation.current !== gen) return;
        setState(fromSummary<R>(key, summary));
        if (summary.running)
          poll(summary.running.id, gen, key, summary.running);
      })
      .catch((err: unknown) => {
        if (generation.current !== gen) return;
        setState({
          ...initial<R>(key),
          phase: "error",
          loadError: clientFacingError(err, "the server could not be reached"),
        });
      });
    return cleanup;
  }, [key, serviceId, subjectId, poll]);

  const follow = React.useCallback(
    (started: AiRunStarted): Promise<AiRun<R>> => {
      const promise = new Promise<AiRun<R>>((resolve) => {
        followers.current.set(started.run_id, resolve);
      });
      const first = placeholder<R>(serviceId, subjectId, started);
      update(key, (s) => ({
        ...s,
        pollRefused: null,
        pastLockUntil: false,
        running: s.running?.id === started.run_id ? s.running : first,
      }));
      poll(started.run_id, generation.current, key, first);
      return promise;
    },
    [key, poll, serviceId, subjectId, update],
  );

  const reconcile = React.useCallback(async (): Promise<void> => {
    const gen = generation.current;
    let summary: AiRunSummary<R>;
    try {
      summary = await fetchers.current.fetchSummary(
        serviceId,
        subjectId ?? undefined,
      );
    } catch (err) {
      if (generation.current !== gen) return;
      if (answeredRefusal(err)) {
        update(key, (s) => ({
          ...s,
          pollRefused: clientFacingError(err, "The runs could not be read."),
        }));
        return;
      }
      console.warn(
        `[useAiRun] could not re-read runs after an unknown outcome: ${String(err)}`,
      );
      return;
    }
    if (generation.current !== gen) return;
    setState(fromSummary<R>(key, summary));
    if (summary.running) poll(summary.running.id, gen, key, summary.running);
  }, [key, poll, serviceId, subjectId, update]);

  // Derived, not reset: a render for new inputs never shows the old ones'
  // runs, even before the effect above has run.
  const current =
    subjectId === null
      ? { ...initial<R>(key), phase: "ready" as const }
      : state.key === key
        ? state
        : initial<R>(key);
  const hide = subjectId === null; // no assessment: no past run describes it
  return {
    ...current,
    latest: hide ? null : current.latest,
    lastCompleted: hide ? null : current.lastCompleted,
    follow,
    reconcile,
  };
}

/** Whether a run belongs to the subject a state key names. */
function scopedTo<R>(run: AiRun<R>, key: string): boolean {
  const subject = key.slice(key.indexOf("|") + 1);
  return subject === "*" || run.subject_id === subject;
}

function fromSummary<R>(key: string, summary: AiRunSummary<R>): State<R> {
  const keep = (r: AiRun<R> | null) => (r && scopedTo(r, key) ? r : null);
  return {
    ...initial<R>(key),
    phase: "ready",
    running: summary.running,
    latest: keep(summary.latest),
    lastCompleted: keep(summary.last_completed),
  };
}
