"use client";
import type { CoverageStatus } from "@/lib/attack/types";

import type { JSX } from "react";

const TONE: Record<CoverageStatus, string> = {
  covered:
    "bg-status-success-bg text-status-success-fg border-status-success-fg",
  partial:
    "bg-status-warning-bg text-status-warning-fg border-status-warning-fg",
  gap: "bg-status-danger-bg text-status-danger-fg border-status-danger-fg",
  not_applicable: "bg-surface-sunken text-ink-tertiary border-border",
  outside_control_surface: "bg-surface-sunken text-ink-secondary border-border",
  // Its own state: not gap red, not N/A grey. Unverified is neither.
  unable_to_determine:
    "bg-status-info-bg text-status-info-fg border-status-info-fg",
};

const LABEL: Record<CoverageStatus, string> = {
  covered: "Covered",
  partial: "Partial",
  gap: "Gap",
  not_applicable: "N/A",
  outside_control_surface: "Outside control surface",
  unable_to_determine: "Not verified",
};

// A status this build does not know. The API enum-types the admin payload, so
// this is reachable only if the API gains a status before the web does -- and
// then it must render as unknown, never throw and never borrow another label.
// The client chip's twin (`AttackDashboard.tsx`) does the same.
const UNKNOWN_LABEL = "Unknown status";
const UNKNOWN_TONE = "bg-surface-sunken text-ink-tertiary border-border";

export interface StatusBadgeProps {
  status: CoverageStatus | null;
  /**
   * #102 / 5.1: the status is assigned but its supporting citation is
   * unconfirmed, so the rollup is withholding this technique from the score.
   */
  pendingReview?: boolean;
}

export function StatusBadge({
  status,
  pendingReview,
}: StatusBadgeProps): JSX.Element {
  if (status === null) {
    return (
      <span className="inline-flex items-center rounded-md border border-dashed border-border px-1.5 py-0.5 text-[10px] font-medium text-ink-tertiary">
        Unscored
      </span>
    );
  }
  const label: string = LABEL[status] ?? UNKNOWN_LABEL;
  const tone: string = TONE[status] ?? UNKNOWN_TONE;
  if (pendingReview) {
    // Its OWN state, which is 5.1's requirement and not a styling preference: a
    // green "Covered" cell over a technique the rollup card is withholding is
    // two surfaces of the same product disagreeing about the same row.
    //
    // Deliberately NOT the gap tone. 5.1 rejected collapsing pending into gap —
    // gap says nothing was found, pending says something was found and is not
    // confirmed — and a consultant reads the colour before the word, so reusing
    // red would make the distinction the copy draws invisible where it counts.
    //
    // The stored status is still named, because it survives underneath: clearing
    // the citation puts the technique back into it. Without that, `pending`
    // reads as a fifth status rather than a held claim.
    return (
      <span
        className="inline-flex items-center rounded-md border border-dashed border-status-info-fg bg-status-info-bg px-1.5 py-0.5 text-[10px] font-semibold text-status-info-fg"
        title={`Assigned ${label.toLowerCase()}, held out of the coverage score until its supporting citation is confirmed.`}
      >
        Pending review ({label.toLowerCase()})
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${tone}`}
    >
      {label}
    </span>
  );
}
