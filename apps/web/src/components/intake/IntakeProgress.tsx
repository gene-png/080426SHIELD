import { cn } from "@shield/design-system";

import { WIZARD_STEPS, type WizardStepKey } from "@/lib/intake/types";

import type { JSX } from "react";

export interface IntakeProgressProps {
  currentStep: WizardStepKey;
  completed: Set<WizardStepKey>;
}

export function IntakeProgress({
  currentStep,
  completed,
}: IntakeProgressProps): JSX.Element {
  const currentIndex = WIZARD_STEPS.findIndex((s) => s.key === currentStep);
  return (
    <ol
      aria-label="Intake progress"
      className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:gap-3"
    >
      {WIZARD_STEPS.map((step, index) => {
        const isCurrent = step.key === currentStep;
        const isComplete = completed.has(step.key);
        const isUpcoming = !isCurrent && !isComplete && index > currentIndex;
        return (
          <li
            key={step.key}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-2 text-sm",
              isCurrent && "border-border-focus bg-brand-50 text-ink-primary",
              isComplete &&
                "border-status-success-border bg-status-success-bg text-status-success-fg",
              isUpcoming &&
                "border-border-subtle bg-surface-card text-ink-tertiary",
              !isCurrent &&
                !isComplete &&
                !isUpcoming &&
                "border-border bg-surface-card text-ink-secondary",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "flex h-5 w-5 items-center justify-center rounded-pill text-xs font-semibold",
                isCurrent && "bg-brand-500 text-ink-on-accent",
                isComplete && "bg-status-success-fg text-ink-on-accent",
                isUpcoming && "border border-border-subtle text-ink-tertiary",
                !isCurrent &&
                  !isComplete &&
                  !isUpcoming &&
                  "bg-ink-disabled text-ink-on-accent",
              )}
            >
              {isComplete ? "✓" : index + 1}
            </span>
            <span className="font-medium">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
