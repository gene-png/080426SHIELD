"use client";
import * as React from "react";

import {
  SUBMIT_ANYWAY,
  blankAnswersMessage,
  goToAreaLabel,
  type BlankAnswersNoun,
} from "./blankAnswersCopy";

import type { JSX } from "react";

export interface BlankArea {
  code: string;
  name: string;
  blank: number;
}

/**
 * #1173: shown in place of submitting when answers are still blank. Lists each
 * area (CSF function, ZT pillar) that has a blank with a button to it, and
 * lets the client submit anyway. Areas with no blank get no button.
 */
export function BlankAnswersWarning({
  areas,
  total,
  noun,
  disabled,
  disabledReason,
  onGoTo,
  onSubmitAnyway,
}: {
  areas: BlankArea[];
  total: number;
  noun: BlankAnswersNoun;
  disabled: boolean;
  /** Why "Submit anyway" is off, when the cause is one the client can fix. */
  disabledReason?: string;
  onGoTo: (code: string) => void;
  onSubmitAnyway: () => void;
}): JSX.Element {
  const ref = React.useRef<HTMLDivElement>(null);
  const messageId = React.useId();
  const reasonId = React.useId();
  // Move focus here when it appears, so a keyboard user who pressed Submit
  // lands on the warning rather than on a button that did nothing visible.
  React.useEffect(() => {
    ref.current?.focus();
  }, []);
  const withBlanks = areas.filter((a) => a.blank > 0);
  const blank = withBlanks.reduce((n, a) => n + a.blank, 0);
  return (
    <div
      ref={ref}
      role="status"
      aria-labelledby={messageId}
      tabIndex={-1}
      className="flex flex-col gap-3 rounded-md border border-status-warning-border bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg"
    >
      <p id={messageId}>{blankAnswersMessage(blank, total, noun)}</p>
      <div className="flex flex-wrap items-center gap-2">
        {withBlanks.map((a) => (
          <button
            key={a.code}
            type="button"
            onClick={() => onGoTo(a.code)}
            className="rounded-md border border-border bg-surface-card px-3 py-1.5 text-sm font-medium text-ink-secondary hover:border-border-strong hover:text-ink-primary"
          >
            {goToAreaLabel(a.name, a.blank)}
          </button>
        ))}
        <button
          type="button"
          onClick={onSubmitAnyway}
          disabled={disabled}
          aria-describedby={disabled && disabledReason ? reasonId : undefined}
          className="rounded-md bg-brand-500 px-4 py-1.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {SUBMIT_ANYWAY}
        </button>
      </div>
      {disabled && disabledReason ? (
        <p id={reasonId}>{disabledReason}</p>
      ) : null}
    </div>
  );
}
