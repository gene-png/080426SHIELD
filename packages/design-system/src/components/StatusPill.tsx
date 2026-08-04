import * as React from "react";

import { cn } from "../utils/cn";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

export interface StatusPillProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone: StatusTone;
  /** Optional dot for high-density operational scans. */
  withDot?: boolean;
}

const TONE_CLASSES: Record<StatusTone, string> = {
  success:
    "bg-status-success-bg text-status-success-fg ring-status-success-border",
  warning:
    "bg-status-warning-bg text-status-warning-fg ring-status-warning-border",
  danger: "bg-status-danger-bg text-status-danger-fg ring-status-danger-border",
  info: "bg-status-info-bg text-status-info-fg ring-status-info-border",
  neutral:
    "bg-status-neutral-bg text-status-neutral-fg ring-status-neutral-border",
};

const DOT_CLASSES: Record<StatusTone, string> = {
  success: "bg-status-success-fg",
  warning: "bg-status-warning-fg",
  danger: "bg-status-danger-fg",
  info: "bg-status-info-fg",
  neutral: "bg-status-neutral-fg",
};

export const StatusPill = React.forwardRef<HTMLSpanElement, StatusPillProps>(
  function StatusPill({ tone, withDot, className, children, ...rest }, ref) {
    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-pill px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
          TONE_CLASSES[tone],
          className,
        )}
        {...rest}
      >
        {withDot ? (
          <span
            className={cn("h-1.5 w-1.5 rounded-pill", DOT_CLASSES[tone])}
            aria-hidden="true"
          />
        ) : null}
        {children}
      </span>
    );
  },
);
