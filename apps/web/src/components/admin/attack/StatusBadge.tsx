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
};

const LABEL: Record<CoverageStatus, string> = {
  covered: "Covered",
  partial: "Partial",
  gap: "Gap",
  not_applicable: "N/A",
};

export interface StatusBadgeProps {
  status: CoverageStatus | null;
}

export function StatusBadge({ status }: StatusBadgeProps): JSX.Element {
  if (status === null) {
    return (
      <span className="inline-flex items-center rounded-md border border-dashed border-border px-1.5 py-0.5 text-[10px] font-medium text-ink-tertiary">
        Unscored
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${TONE[status]}`}
    >
      {LABEL[status]}
    </span>
  );
}
