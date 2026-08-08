import * as React from "react";

import { cn } from "../utils/cn";
import { Card } from "./Card";

import type { JSX } from "react";

export interface NumberCardProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  value: string | number;
  /** Optional human-readable delta, e.g. "+3 this week" or "-12% vs last month". */
  delta?: string;
  deltaTone?: "positive" | "negative" | "neutral";
  /** Optional helper line under the delta. */
  hint?: string;
}

const DELTA_TONE: Record<NonNullable<NumberCardProps["deltaTone"]>, string> = {
  positive: "text-status-success-fg",
  negative: "text-status-danger-fg",
  neutral: "text-ink-secondary",
};

/**
 * Step the value's type size down as it gets longer.
 *
 * These cards sit in a 5-across grid, so the box is narrow while the value is
 * whatever the data says. At a fixed `text-3xl` a real annual-cost figure —
 * "$3,608,000" — ran outside its card on the Tech Debt workspace: the number a
 * consultant is there to read was the one thing they could not read.
 *
 * Stepping the size beats truncation (an ellipsised currency figure is worse
 * than a small one — "$3,608…" is not a number) and beats wrapping (a wrapped
 * figure changes card heights and breaks the row alignment the grid exists for).
 * The thresholds are character counts because that is what actually overflows;
 * commas and currency symbols occupy space just like digits do.
 */
function valueSizeClass(value: string | number): string {
  const length = String(value).length;
  if (length <= 6) return "text-3xl";
  if (length <= 9) return "text-2xl";
  if (length <= 13) return "text-xl";
  return "text-lg";
}

export function NumberCard({
  label,
  value,
  delta,
  deltaTone = "neutral",
  hint,
  className,
  ...rest
}: NumberCardProps): JSX.Element {
  return (
    // min-w-0 is load-bearing: without it a grid item refuses to shrink below
    // its content's intrinsic width, so a long value pushes the card past its
    // column instead of the text adapting.
    <Card className={cn("min-w-0 p-6", className)} {...rest}>
      <p className="truncate text-xs font-medium uppercase tracking-wider text-ink-tertiary">
        {label}
      </p>
      <p
        // tabular-nums keeps digits on a fixed advance so figures line up
        // between cards; break-words is the last-resort guard for a single
        // unbroken token longer than any size step anticipated.
        className={cn(
          "mt-2 break-words font-semibold leading-tight tabular-nums text-ink-primary",
          valueSizeClass(value),
        )}
        title={String(value)}
      >
        {value}
      </p>
      {delta ? (
        <p className={cn("mt-2 text-sm font-medium", DELTA_TONE[deltaTone])}>
          {delta}
        </p>
      ) : null}
      {hint ? <p className="mt-1 text-xs text-ink-tertiary">{hint}</p> : null}
    </Card>
  );
}
