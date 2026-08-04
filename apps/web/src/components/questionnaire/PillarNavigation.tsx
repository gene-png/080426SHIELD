"use client";
import * as React from "react";

import { cn } from "@shield/design-system";

import type { QuestionnaireSection } from "./types";

import type { JSX } from "react";

export interface PillarNavigationProps {
  sections: QuestionnaireSection[];
  activeId: string;
  onChange: (id: string) => void;
  /** Per-section completion fractions (0-1). Drives the progress bar + count. */
  progress?: Record<string, number>;
}

/**
 * Page-per-pillar navigation: shows one section ("pillar") at a time with
 * Previous / Next controls and a "Section N of M" step counter, replacing the
 * horizontal tab strip. Keeps the same (sections, activeId, onChange) contract
 * as the old SectionTabs so callers don't change.
 */
export function PillarNavigation({
  sections,
  activeId,
  onChange,
  progress,
}: PillarNavigationProps): JSX.Element {
  const total = sections.length;
  const idx = Math.max(
    0,
    sections.findIndex((s) => s.id === activeId),
  );
  const active = sections[idx];
  const pct = progress?.[active?.id ?? ""] ?? 0;
  const completed = sections.filter((s) => (progress?.[s.id] ?? 0) >= 1).length;

  function goTo(next: number): void {
    if (next < 0 || next >= total) return;
    onChange(sections[next].id);
  }

  const atFirst = idx <= 0;
  const atLast = idx >= total - 1;

  return (
    <div className="flex flex-col gap-3 border-b border-border-subtle pb-3">
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-tertiary">
            Section {idx + 1} of {total}
          </p>
          <p className="truncate text-base font-semibold text-ink-primary">
            {active?.title}
          </p>
        </div>
        {progress ? (
          <span className="shrink-0 text-xs font-medium text-ink-tertiary">
            {completed}/{total} complete
          </span>
        ) : null}
      </div>

      {progress ? (
        <div
          className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-sunken"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct * 100)}
          aria-label={`${active?.title ?? "Section"} ${Math.round(pct * 100)}% complete`}
        >
          <div
            className="h-full rounded-pill bg-brand-500 transition-all"
            style={{ width: `${Math.round(pct * 100)}%` }}
          />
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => goTo(idx - 1)}
          disabled={atFirst}
          className={cn(
            "rounded-md border px-3 py-1.5 text-sm font-medium transition",
            atFirst
              ? "cursor-not-allowed border-border-subtle text-ink-tertiary opacity-50"
              : "border-border text-ink-secondary hover:bg-surface-sunken hover:text-ink-primary",
          )}
        >
          ← Previous
        </button>
        <button
          type="button"
          onClick={() => goTo(idx + 1)}
          disabled={atLast}
          className={cn(
            "rounded-md border px-4 py-1.5 text-sm font-semibold transition",
            atLast
              ? "cursor-not-allowed border-border-subtle text-ink-tertiary opacity-50"
              : "border-brand-500 bg-brand-500 text-ink-on-accent hover:bg-brand-600",
          )}
        >
          Next →
        </button>
      </div>
    </div>
  );
}
