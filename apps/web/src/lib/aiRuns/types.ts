/**
 * Run-AI runs (#645). A Run-AI answers 202 with a run to poll; the work
 * happens in a background job on the api, and the run row is what the
 * workspace reads -- including, once it completes, every disclosure about
 * what it did, so those survive a reload (#271).
 *
 * Mirrors `apps/api/app/schemas/ai_runs.py`.
 */

/** What the consultant acknowledged a Run-AI would do. */
export type AiServes = "live" | "offline";

/** The 202 a Run-AI POST answers with. */
export interface AiRunStarted {
  run_id: string;
  status: "running";
  serves: AiServes;
  /** When the run's job gives up. */
  deadline_at: string;
  /** The latest the run can hold the edit lock: what "locked until" says. */
  lock_until: string;
  /** True when this POST joined a run already in progress. */
  joined: boolean;
}

/** One run, as polled. `R` is the service's own result shape. */
export interface AiRun<R> {
  id: string;
  service_id: string;
  /** What the run worked on: the assessment, or the Tech Debt document. */
  subject_id: string;
  purpose: string;
  status: "running" | "completed" | "failed";
  serves: AiServes;
  started_at: string;
  deadline_at: string;
  lock_until: string;
  finished_at: string | null;
  batches_total: number | null;
  batches_failed: number | null;
  applied_count: number | null;
  /** Every disclosure about the run. NULL until it completes. */
  result: R | null;
  error_reason: string | null;
  error_message: string | null;
  /** NULL is "not known", never "no". */
  charged_likely: boolean | null;
}

/**
 * What a workspace needs on load. `last_completed` is separate from `latest`
 * (#271): a later total failure must not hide an earlier run whose results
 * still stand in the assessment.
 */
export interface AiRunSummary<R> {
  running: AiRun<R> | null;
  latest: AiRun<R> | null;
  last_completed: AiRun<R> | null;
}
