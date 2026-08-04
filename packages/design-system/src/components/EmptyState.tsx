import * as React from "react";

import { cn } from "../utils/cn";

import type { JSX } from "react";

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Required short heading describing the empty state. */
  title: string;
  description?: string;
  /** Optional icon (e.g. a lucide icon). */
  icon?: React.ReactNode;
  /** Optional primary action - button or link rendered by the caller. */
  action?: React.ReactNode;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
  ...rest
}: EmptyStateProps): JSX.Element {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-surface-card px-6 py-12 text-center",
        className,
      )}
      {...rest}
    >
      {icon ? <div className="text-ink-tertiary">{icon}</div> : null}
      <h3 className="text-base font-semibold text-ink-primary">{title}</h3>
      {description ? (
        <p className="max-w-prose text-sm text-ink-secondary">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
