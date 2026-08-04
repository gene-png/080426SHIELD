import * as React from "react";

import { cn } from "@shield/design-system";

import type { JSX } from "react";

export interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}

/** USWDS-style form field with accessible label/hint/error wiring. */
export function Field({
  id,
  label,
  hint,
  error,
  required,
  children,
  className,
}: FieldProps): JSX.Element {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink-primary">
        {label}
        {required ? (
          <span aria-hidden="true" className="ml-1 text-status-danger-fg">
            *
          </span>
        ) : null}
      </label>
      {React.cloneElement(
        children as React.ReactElement<React.HTMLAttributes<HTMLElement>>,
        {
          "aria-describedby":
            [hintId, errorId].filter(Boolean).join(" ") || undefined,
          "aria-invalid": error ? "true" : undefined,
        },
      )}
      {hint ? (
        <p id={hintId} className="text-xs text-ink-tertiary">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-xs text-status-danger-fg" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const inputClasses =
  "rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden aria-[invalid=true]:border-status-danger-fg";

export const textareaClasses =
  "rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden aria-[invalid=true]:border-status-danger-fg min-h-[7rem] resize-vertical";

export const selectClasses =
  "rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden aria-[invalid=true]:border-status-danger-fg";
