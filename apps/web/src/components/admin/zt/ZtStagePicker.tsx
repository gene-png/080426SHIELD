"use client";
import * as React from "react";

import type { CatalogStage } from "@/lib/zt/types";

import type { JSX } from "react";

export interface ZtStagePickerProps {
  value: number | null;
  onChange: (next: number | null) => void;
  disabled?: boolean;
  ariaLabel?: string;
  stages: CatalogStage[];
}

export function ZtStagePicker({
  value,
  onChange,
  disabled = false,
  ariaLabel,
  stages,
}: ZtStagePickerProps): JSX.Element {
  const radioRefs = React.useRef<Array<HTMLButtonElement | null>>([]);
  const count = stages.length;
  const selectedIndex = stages.findIndex(({ stage }) => stage === value);

  // Roving tabindex: exactly one radio is a Tab stop — the selected one, or the
  // first when nothing is selected. Arrow keys move focus (and the roving stop)
  // between radios; they do NOT change the selection. We deliberately keep
  // select-on-Space/Enter (not the standard select-on-focus radiogroup variant)
  // because selecting fires an auto-save PATCH — moving selection on every
  // arrow keypress would flood the answers endpoint. See s3/s6 auto-save flows.
  const [focusIndex, setFocusIndex] = React.useState<number>(
    selectedIndex >= 0 ? selectedIndex : 0,
  );
  // Snap the roving tab stop to the selection whenever it changes, without an
  // effect: the sanctioned "adjust state during render" pattern (guarded by a
  // stored previous value so it runs once per selection change, not every
  // render). react-hooks v6 set-state-in-effect flags the effect form.
  const [prevSelected, setPrevSelected] = React.useState(selectedIndex);
  if (selectedIndex !== prevSelected) {
    setPrevSelected(selectedIndex);
    if (selectedIndex >= 0) setFocusIndex(selectedIndex);
  }

  function handleKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ): void {
    if (count === 0) return;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      next = (index + 1) % count;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = (index - 1 + count) % count;
    }
    if (next === null) return;
    event.preventDefault();
    setFocusIndex(next);
    radioRefs.current[next]?.focus();
  }

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel ?? "Maturity stage"}
      className="flex flex-wrap gap-1"
    >
      {stages.map(({ stage, label }, index) => {
        const active = value === stage;
        return (
          <button
            key={stage}
            ref={(el) => {
              radioRefs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={index === focusIndex ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(active ? null : stage)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={[
              "rounded-md px-2.5 py-1 text-xs font-semibold border transition",
              active
                ? "border-brand-500 bg-brand-500 text-ink-on-accent"
                : "border-border bg-surface-card text-ink-secondary hover:bg-surface-sunken",
              disabled ? "cursor-not-allowed opacity-50" : "",
            ].join(" ")}
            title={label}
          >
            S{stage}
            <span className="ml-1 hidden font-medium normal-case sm:inline">
              {label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
