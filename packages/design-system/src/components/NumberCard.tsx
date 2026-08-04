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
    <Card className={cn("p-6", className)} {...rest}>
      <p className="text-xs font-medium uppercase tracking-wider text-ink-tertiary">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold leading-tight text-ink-primary">
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
