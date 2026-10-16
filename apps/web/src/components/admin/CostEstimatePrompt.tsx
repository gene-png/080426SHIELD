"use client";

import * as React from "react";

import { RunAiGuard } from "@/components/admin/RunAiGuard";
import type { AiServes } from "@/lib/aiRuns/types";
import {
  ENTER_COSTS,
  ESTIMATE_DISCLOSURE,
  LET_AI_ESTIMATE,
  estimatePromptText,
} from "@/lib/tech_debt/costEstimate";

import type { JSX } from "react";

/**
 * TD-5 (for #1060): the workspace's "no cost" prompt, copy E1 to E3 (approved
 * on #736 6205600298, ruled 6206818759 item 5).
 *
 * Shown only on an editable list with at least one uncosted source row. E3,
 * the disclosure, sits beside the button that starts the run, so it is read
 * before the run starts. "Let AI estimate" is a Run-AI and goes through
 * `RunAiGuard`: an unreadable AI status fails closed, and offline output needs
 * the admin's acknowledgement.
 */
export function CostEstimatePrompt({
  noCostCount,
  editable,
  busy,
  onEnterCosts,
  onEstimate,
}: {
  noCostCount: number;
  editable: boolean;
  /** True while an estimate (or any run on this service) is in progress. */
  busy: boolean;
  onEnterCosts: () => void;
  onEstimate: (serves: AiServes) => void;
}): JSX.Element | null {
  if (!editable || noCostCount <= 0) return null;
  return (
    <div
      className="rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm"
      role="status"
      aria-label="Tools with no cost"
      data-testid="cost-estimate-prompt"
    >
      <p className="font-semibold text-status-warning-fg">
        {estimatePromptText(noCostCount)}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onEnterCosts}
          className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50"
        >
          {ENTER_COSTS}
        </button>
        <RunAiGuard onProceed={onEstimate}>
          {({ onClick, statusUnknown }) => (
            <button
              type="button"
              onClick={onClick}
              disabled={busy || statusUnknown}
              className="rounded bg-brand-600 px-3 py-1 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {LET_AI_ESTIMATE}
            </button>
          )}
        </RunAiGuard>
      </div>
      <p className="mt-2 text-ink-secondary">{ESTIMATE_DISCLOSURE}</p>
    </div>
  );
}
