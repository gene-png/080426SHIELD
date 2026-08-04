"use client";
import * as React from "react";

import { cn } from "@shield/design-system";

import type { QuestionnaireSection } from "./types";

import type { JSX } from "react";

export interface SectionTabsProps {
  sections: QuestionnaireSection[];
  activeId: string;
  onChange: (id: string) => void;
  /** Per-section completion fractions (0-1). Drives the small progress chip. */
  progress?: Record<string, number>;
}

/**
 * Horizontally-scrolling tab strip with full keyboard support
 * (arrow keys, Home/End) per WAI-ARIA APG "Tabs with Manual Activation".
 * Activation is on click + arrow keys; reading order matches tab order.
 */
export function SectionTabs({
  sections,
  activeId,
  onChange,
  progress,
}: SectionTabsProps): JSX.Element {
  const tabRefs = React.useRef<Record<string, HTMLButtonElement | null>>({});

  function focusTab(id: string): void {
    tabRefs.current[id]?.focus();
  }

  function onKeyDown(
    e: React.KeyboardEvent<HTMLButtonElement>,
    idx: number,
  ): void {
    if (sections.length === 0) return;
    let nextIdx: number | null = null;
    if (e.key === "ArrowRight") nextIdx = (idx + 1) % sections.length;
    else if (e.key === "ArrowLeft")
      nextIdx = (idx - 1 + sections.length) % sections.length;
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = sections.length - 1;
    if (nextIdx === null) return;
    e.preventDefault();
    const id = sections[nextIdx].id;
    onChange(id);
    focusTab(id);
  }

  return (
    <div
      role="tablist"
      aria-label="Questionnaire sections"
      className="flex flex-wrap gap-1 border-b border-border-subtle"
    >
      {sections.map((section, idx) => {
        const isActive = section.id === activeId;
        const pct = progress?.[section.id] ?? 0;
        return (
          <button
            key={section.id}
            ref={(el) => {
              tabRefs.current[section.id] = el;
            }}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={`section-${section.id}`}
            id={`tab-${section.id}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(section.id)}
            onKeyDown={(e) => onKeyDown(e, idx)}
            className={cn(
              "flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "border-brand-500 text-ink-primary"
                : "border-transparent text-ink-secondary hover:border-border hover:text-ink-primary",
            )}
          >
            <span>{section.title}</span>
            {progress ? (
              <span
                aria-label={`${Math.round(pct * 100)}% complete`}
                className={cn(
                  "rounded-pill px-1.5 py-0.5 text-xs font-semibold",
                  pct === 1
                    ? "bg-status-success-bg text-status-success-fg"
                    : pct > 0
                      ? "bg-status-info-bg text-status-info-fg"
                      : "bg-surface-sunken text-ink-tertiary",
                )}
              >
                {Math.round(pct * 100)}%
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
