"use client";
import * as React from "react";

import { Field, inputClasses, textareaClasses } from "../Field";
import type { ServiceRequestInput, ServiceType } from "@/lib/intake/types";

/**
 * One deadline and one block of context, applied across the selected services.
 *
 * Step 5 asked for a deadline and notes per service, so a client requesting all
 * four typed the same date and the same paragraph four times (UX finding 8).
 *
 * These values are a FORM CONVENIENCE, not a stored concept. Applying them
 * writes per-service values and nothing else persists — no engagement-level
 * default that every later reader would have to resolve against an override.
 * That ambiguity is exactly the kind that leaks into a report and gets
 * presented to a client as fact.
 *
 * Applying only fills fields that are still EMPTY. The finding asks for
 * "shared defaults with optional service-specific overrides", and silently
 * overwriting a deadline someone deliberately set for one service would
 * destroy the override rather than provide a default.
 */

export interface SharedServiceDefaultsProps {
  services: ServiceType[];
  serviceInputs: Record<ServiceType, ServiceRequestInput>;
  onApply: (patch: { deadline?: string; notes?: string }) => void;
}

export function SharedServiceDefaults({
  services,
  serviceInputs,
  onApply,
}: SharedServiceDefaultsProps): React.ReactElement | null {
  const [deadline, setDeadline] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [applied, setApplied] = React.useState<string | null>(null);

  // Below two services there is nothing to share — the per-service fields are
  // already the shortest path.
  if (services.length < 2) return null;

  const wouldFillDeadline = deadline
    ? services.filter((s) => !serviceInputs[s]?.deadline).length
    : 0;
  const wouldFillNotes = notes.trim()
    ? services.filter((s) => !serviceInputs[s]?.notes).length
    : 0;
  const canApply = wouldFillDeadline > 0 || wouldFillNotes > 0;

  function apply(): void {
    onApply({
      deadline: deadline ? new Date(deadline).toISOString() : undefined,
      notes: notes.trim() || undefined,
    });
    const parts: string[] = [];
    if (wouldFillDeadline > 0) {
      parts.push(
        `deadline on ${wouldFillDeadline} service${wouldFillDeadline === 1 ? "" : "s"}`,
      );
    }
    if (wouldFillNotes > 0) {
      parts.push(
        `context on ${wouldFillNotes} service${wouldFillNotes === 1 ? "" : "s"}`,
      );
    }
    setApplied(`Applied ${parts.join(" and ")}.`);
  }

  return (
    <section
      aria-labelledby="shared-defaults-heading"
      className="rounded-md border border-border-subtle bg-surface-sunken p-4"
    >
      <h3
        id="shared-defaults-heading"
        className="text-sm font-semibold text-ink-primary"
      >
        Shared across your services
      </h3>
      <p className="mt-1 text-sm text-ink-secondary">
        Fill these once and apply them to every service you picked. Anything you
        have already set for a specific service is left alone — apply fills the
        blanks only.
      </p>

      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          id="shared-deadline"
          label="Target deadline"
          hint="Optional. Applies to services with no deadline yet."
        >
          <input
            id="shared-deadline"
            type="date"
            value={deadline}
            onChange={(e) => {
              setDeadline(e.target.value);
              setApplied(null);
            }}
            className={inputClasses}
          />
        </Field>
        <Field
          id="shared-notes"
          label="General context"
          className="sm:col-span-2"
          hint="Applies to services with no notes yet."
        >
          <textarea
            id="shared-notes"
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              setApplied(null);
            }}
            className={textareaClasses}
            rows={3}
          />
        </Field>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={apply}
          disabled={!canApply}
          className="rounded bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Apply to my services
        </button>
        {/* Say what happened. A button that silently fills fields further down
            the page, several of them collapsed, is indistinguishable from one
            that did nothing. */}
        <span role="status" className="text-sm text-ink-secondary">
          {applied ??
            (canApply
              ? `Will fill ${wouldFillDeadline > 0 ? `${wouldFillDeadline} deadline${wouldFillDeadline === 1 ? "" : "s"}` : ""}${wouldFillDeadline > 0 && wouldFillNotes > 0 ? " and " : ""}${wouldFillNotes > 0 ? `${wouldFillNotes} notes field${wouldFillNotes === 1 ? "" : "s"}` : ""}.`
              : "")}
        </span>
      </div>
    </section>
  );
}
