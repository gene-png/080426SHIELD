"use client";
import * as React from "react";

import type { StatusTone } from "./StatusPill";
import { cn } from "../utils/cn";

import type { JSX } from "react";

export interface ToastInput {
  title: string;
  description?: string;
  tone?: StatusTone;
  /** Milliseconds before auto-dismiss. Pass 0 to make sticky. */
  durationMs?: number;
}

interface ToastInternal extends Required<Omit<ToastInput, "description">> {
  id: string;
  description?: string;
}

interface ToastContextValue {
  toast: (input: ToastInput) => string;
  dismiss: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside <ToastProvider>.");
  }
  return ctx;
}

const TONE_CLASSES: Record<StatusTone, string> = {
  success:
    "border-status-success-border bg-status-success-bg text-status-success-fg",
  warning:
    "border-status-warning-border bg-status-warning-bg text-status-warning-fg",
  danger:
    "border-status-danger-border bg-status-danger-bg text-status-danger-fg",
  info: "border-status-info-border bg-status-info-bg text-status-info-fg",
  neutral: "border-border-subtle bg-surface-card text-ink-primary",
};

export function ToastProvider({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  const [toasts, setToasts] = React.useState<ToastInternal[]>([]);
  const idRef = React.useRef(0);

  const dismiss = React.useCallback((id: string) => {
    setToasts((curr) => curr.filter((t) => t.id !== id));
  }, []);

  const toast = React.useCallback(
    (input: ToastInput) => {
      const id = `t${++idRef.current}`;
      const next: ToastInternal = {
        id,
        title: input.title,
        description: input.description,
        tone: input.tone ?? "neutral",
        durationMs: input.durationMs ?? 5000,
      };
      setToasts((curr) => [...curr, next]);
      if (next.durationMs > 0) {
        setTimeout(() => dismiss(id), next.durationMs);
      }
      return id;
    },
    [dismiss],
  );

  const value = React.useMemo(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed right-4 top-4 z-toast flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto rounded-md border px-4 py-3 shadow-md",
              TONE_CLASSES[t.tone],
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold">{t.title}</p>
                {t.description ? (
                  <p className="mt-1 text-sm opacity-90">{t.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                aria-label="Dismiss notification"
                className="text-sm font-medium opacity-70 hover:opacity-100 focus:outline-hidden focus-visible:opacity-100"
                onClick={() => dismiss(t.id)}
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
