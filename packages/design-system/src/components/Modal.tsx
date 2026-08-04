"use client";
import * as React from "react";

import { cn } from "../utils/cn";

import type { JSX } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  /** Visible heading - required for the dialog's accessible name. */
  title: React.ReactNode;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE: Record<NonNullable<ModalProps["size"]>, string> = {
  sm: "max-w-md",
  md: "max-w-xl",
  lg: "max-w-3xl",
};

/**
 * Native `<dialog>`-backed modal.
 *
 * The browser handles focus trap, ESC-to-close, and ARIA dialog semantics.
 * We just wire the `open` prop to `showModal()` / `close()` and surface
 * the `close` event (ESC, outside click via form-cancel, or programmatic).
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  className,
}: ModalProps): JSX.Element {
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
        "w-full rounded-lg border border-border-subtle bg-surface-card p-0 text-ink-primary shadow-lg backdrop:bg-surface-overlay",
        SIZE[size],
        className,
      )}
    >
      <div className="flex flex-col">
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
        <div className="px-6 py-5">{children}</div>
        {footer ? (
          <footer className="flex items-center justify-end gap-2 border-t border-border-subtle px-6 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </dialog>
  );
}
