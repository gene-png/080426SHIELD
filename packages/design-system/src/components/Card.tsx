import * as React from "react";

import { cn } from "../utils/cn";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Visual weight - `flat` removes the shadow for inline contexts. */
  variant?: "raised" | "flat";
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(function Card(
  { variant = "raised", className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        "rounded-lg border border-border-subtle bg-surface-card",
        variant === "raised" && "shadow-sm",
        className,
      )}
      {...rest}
    />
  );
});

export const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(function CardHeader({ className, ...rest }, ref) {
  return (
    <div
      ref={ref}
      className={cn(
        "flex flex-col gap-1 border-b border-border-subtle px-6 py-4",
        className,
      )}
      {...rest}
    />
  );
});

export const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(function CardTitle({ className, ...rest }, ref) {
  return (
    <h3
      ref={ref}
      className={cn("text-base font-semibold text-ink-primary", className)}
      {...rest}
    />
  );
});

export const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(function CardDescription({ className, ...rest }, ref) {
  return (
    <p
      ref={ref}
      className={cn("text-sm text-ink-secondary", className)}
      {...rest}
    />
  );
});

export const CardBody = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(function CardBody({ className, ...rest }, ref) {
  return <div ref={ref} className={cn("px-6 py-5", className)} {...rest} />;
});

export const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(function CardFooter({ className, ...rest }, ref) {
  return (
    <div
      ref={ref}
      className={cn(
        "flex items-center justify-end gap-2 border-t border-border-subtle px-6 py-3",
        className,
      )}
      {...rest}
    />
  );
});
