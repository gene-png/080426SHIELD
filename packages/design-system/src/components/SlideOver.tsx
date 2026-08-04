"use client";
import * as React from "react";

import { cn } from "../utils/cn";

import type { JSX } from "react";

export interface SlideOverProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  side?: "right" | "left";
  /** Width preset. Defaults to `md` (28rem) - tuned for context panels. */
  width?: "sm" | "md" | "lg";
  className?: string;
}

const WIDTH: Record<NonNullable<SlideOverProps["width"]>, string> = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
};

const SIDE_POS: Record<NonNullable<SlideOverProps["side"]>, string> = {
  right: "ml-auto mr-0",
  left: "mr-auto ml-0",
};

/**
 * Native `<dialog>`-backed side panel. Same accessibility model as Modal -
 * the browser provides focus trap, ESC, ARIA. The visual difference is
 * full-height, edge-anchored.
 */
export function SlideOver({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  side = "right",
  width = "md",
  className,
}: SlideOverProps): JSX.Element {
  const ref = React.useRef<HTMLDialogElement | null>(null);
  const titleId = React.useId();
  const descId = React.useId();

  React.useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      dlg.showModal();
    } else if (!open && dlg.open) {
      dlg.close();
    }
  }, [open]);

  React.useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    const handleClose = () => onClose();
    dlg.addEventListener("close", handleClose);
    return () => dlg.removeEventListener("close", handleClose);
  }, [onClose]);

  function handleBackdropClick(e: React.MouseEvent<HTMLDialogElement>): void {
    if (e.target === ref.current) {
      ref.current?.close();
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onClick={handleBackdropClick}
      className={cn(
        "h-full max-h-none w-full border-l border-border-subtle bg-surface-card p-0 text-ink-primary shadow-lg backdrop:bg-surface-overlay",
        WIDTH[width],
        SIDE_POS[side],
        className,
      )}
    >
      <div className="flex h-full flex-col">
        <header className="border-b border-border-subtle px-6 py-4">
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          {description ? (
            <p id={descId} className="mt-1 text-sm text-ink-secondary">
              {description}
            </p>
          ) : null}
        </header>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer ? (
          <footer className="flex items-center justify-end gap-2 border-t border-border-subtle px-6 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </dialog>
  );
}
