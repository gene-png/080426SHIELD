"use client";
import * as React from "react";

import { Card, CardBody } from "@shield/design-system";

import type { JSX } from "react";

/**
 * A numbered step in an admin workspace.
 *
 * Workspaces grew section by section, so their order reflected the order the
 * features were built rather than the order a consultant works: on the ATT&CK
 * page the matrix — the actual review, and the longest task on the page — sat
 * BELOW the deliverable and the message thread. Nothing said what to do first,
 * or what "done" looked like.
 *
 * Each step therefore carries three things: where it sits in the sequence, what
 * it is for in one sentence, and whether it can be acted on yet. `blockedReason`
 * is deliberately a sentence rather than a boolean — "you cannot do this yet" is
 * useless without "because", and the consultant needs to know which earlier step
 * to go back to.
 */
export function WorkflowStep({
  number,
  title,
  description,
  blockedReason,
  done,
  children,
}: {
  number: number;
  title: string;
  description: string;
  /** Set when an earlier step must happen first. Explains which, and why. */
  blockedReason?: string | null;
  /** Marks the step visibly complete so a returning admin sees where they are. */
  done?: boolean;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <Card>
      <CardBody className="flex flex-col gap-3">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
              done
                ? "bg-status-success-fg text-ink-on-accent"
                : blockedReason
                  ? "bg-surface-muted text-ink-tertiary"
                  : "bg-brand-500 text-ink-on-accent"
            }`}
          >
            {done ? "✓" : number}
          </span>
          <div className="min-w-0">
            {/* The number is in the heading text, not only in the badge above:
                the badge is aria-hidden decoration, so without this a screen
                reader would hear an unordered pile of sections. */}
            <h2 className="text-base font-semibold text-ink-primary">
              {`Step ${number}: ${title}`}
              {done ? " — done" : ""}
            </h2>
            <p className="max-w-prose text-sm text-ink-secondary">
              {description}
            </p>
          </div>
        </div>
        {blockedReason ? (
          <p className="text-sm text-ink-tertiary" role="note">
            {blockedReason}
          </p>
        ) : null}
        <div className={blockedReason ? "opacity-60" : undefined}>
          {children}
        </div>
      </CardBody>
    </Card>
  );
}
