"use client";
import * as React from "react";

/**
 * One progress vocabulary across all four services.
 *
 * Relabelling only: nothing here changes a service's state machine, its routes
 * or its audit vocabulary. The upstream derives these stages read-only from
 * status plus evidence already in the database, so this component renders a
 * view of existing state and never a new one.
 *
 * `prepare` deliberately means something slightly different per service: for
 * Zero Trust and CSF it is the client submitting their self-assessment, and for
 * Tech Debt and ATT&CK — which have no client-input step at all — it is simply
 * the version existing. Showing a stage that could never light for half the
 * services would read as a permanently broken step rather than an absent one.
 */

export type StageState = "complete" | "current" | "pending";

export interface Stage {
  key: string;
  state: StageState;
}

/** Service kinds whose `prepare` stage waits on a client self-assessment. */
const CLIENT_INPUT_KINDS = new Set([
  "zero_trust_cisa",
  "zero_trust_dod",
  "nist_csf",
]);

const LABELS: Record<string, string> = {
  prepare: "Prepare",
  analyze: "Analyze",
  review: "Review",
  approve: "Approve",
  generate: "Generate",
  release: "Release",
};

function prepareLabel(kind: string | undefined): string {
  return kind && CLIENT_INPUT_KINDS.has(kind) ? "Self-assessment" : "Prepare";
}

function label(key: string, kind: string | undefined): string {
  return key === "prepare" ? prepareLabel(kind) : (LABELS[key] ?? key);
}

const DOT: Record<StageState, string> = {
  complete: "bg-brand-600 border-brand-600",
  current: "bg-white border-brand-600 ring-2 ring-brand-200",
  pending: "bg-slate-100 border-slate-300",
};

const TEXT: Record<StageState, string> = {
  complete: "text-slate-700",
  current: "text-brand-700 font-semibold",
  pending: "text-slate-400",
};

/** Screen-reader wording — the dot colours alone are not an accessible status. */
const SPOKEN: Record<StageState, string> = {
  complete: "completed",
  current: "in progress",
  pending: "not started",
};

export function ProgressStages({
  stages,
  kind,
  version,
}: {
  stages: Stage[];
  kind?: string;
  version?: number | null;
}): React.ReactElement | null {
  if (!stages.length) return null;

  return (
    <nav
      aria-label="Assessment progress"
      className="w-full overflow-x-auto"
      data-testid="progress-stages"
    >
      <ol className="flex min-w-max items-center gap-1 py-2">
        {stages.map((stage, i) => (
          <li key={stage.key} className="flex items-center gap-1">
            <div className="flex items-center gap-2 px-1">
              <span
                aria-hidden="true"
                className={`h-3 w-3 shrink-0 rounded-full border-2 ${DOT[stage.state]}`}
              />
              <span
                className={`whitespace-nowrap text-sm ${TEXT[stage.state]}`}
              >
                {label(stage.key, kind)}
              </span>
              {/* The visual state is colour-only, so state it in text too. */}
              <span className="sr-only">
                {": "}
                {SPOKEN[stage.state]}
              </span>
            </div>
            {i < stages.length - 1 ? (
              <span
                aria-hidden="true"
                className={`h-px w-6 shrink-0 ${
                  stage.state === "complete" ? "bg-brand-600" : "bg-slate-200"
                }`}
              />
            ) : null}
          </li>
        ))}
      </ol>
      {typeof version === "number" ? (
        <p className="sr-only">Version {version}.</p>
      ) : null}
    </nav>
  );
}
