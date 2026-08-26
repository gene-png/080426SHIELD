"use client";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import {
  confirmSecurityClassification,
  overrideSecurityClassification,
} from "@/lib/tech_debt/client";
import type {
  CapabilityItem,
  CapabilityList,
  SecurityFunction,
} from "@/lib/tech_debt/types";

/**
 * Sign-off queue for NEGATIVE security classifications.
 *
 * Tech Debt covers the whole software portfolio, so the AI now classifies each
 * capability rather than dropping the non-security ones. That classification is
 * load-bearing: it decides what the ATT&CK mapping is allowed to cite, and a
 * tool missing from that list cannot be named by the model at all — so the
 * technique it covers reads as uncovered rather than unassessed.
 *
 * A wrongly-excluded security tool is therefore a much worse failure than a
 * payroll system getting a second look. Until a consultant agrees, the negative
 * is provisional and the row stays in the ATT&CK subset. This queue is where
 * that provisional state becomes visible and finite.
 */

const FUNCTIONS: SecurityFunction[] = ["prevent", "detect", "respond"];

function awaitingSignoff(item: CapabilityItem): boolean {
  return item.security_related === false && !item.security_class_confirmed;
}

export function SecurityClassificationQueue({
  list,
  onUpdated,
  editable,
}: {
  list: CapabilityList;
  onUpdated: (next: CapabilityList) => void;
  editable: boolean;
}): React.ReactElement | null {
  const pending = React.useMemo(
    () => (list.items ?? []).filter(awaitingSignoff),
    [list.items],
  );
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [picked, setPicked] = React.useState<
    Record<string, SecurityFunction[]>
  >({});

  if (pending.length === 0) return null;

  async function run(fn: () => Promise<CapabilityList>, itemId: string) {
    setBusyId(itemId);
    setError(null);
    try {
      onUpdated(await fn());
    } catch (err) {
      // Fail loudly: leave the row in the queue and say what happened, rather
      // than quietly dropping the sign-off and looking like it worked.
      setError(
        err instanceof Error
          ? `Couldn't record that: ${err.message}`
          : "Couldn't record that.",
      );
    } finally {
      setBusyId(null);
    }
  }

  function toggle(itemId: string, fn: SecurityFunction) {
    setPicked((prev) => {
      const cur = prev[itemId] ?? [];
      return {
        ...prev,
        [itemId]: cur.includes(fn) ? cur.filter((f) => f !== fn) : [...cur, fn],
      };
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Confirm security classification ({pending.length})
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="max-w-prose text-sm text-ink-secondary">
          The AI classified these as <strong>not security-related</strong>.
          Until you agree, they stay in the ATT&amp;CK tool mapping — a security
          tool dropped by mistake cannot be cited there at all, and its absence
          would read as a coverage gap rather than a missing input.
        </p>

        {error ? (
          <p
            role="alert"
            className="text-sm font-medium text-status-danger-fg"
            /* `danger-600` is not a token. The preset defines
             status.danger-fg/bg/border and no numeric danger scale, so
             this alert rendered with no colour at all. Found while
             adding the same class to the audit viewer -- a twin, fixed
             rather than left, since an uncoloured role="alert" is the
             one place the styling carries meaning. */
          >
            {error}
          </p>
        ) : null}

        <ul className="divide-y divide-slate-200">
          {pending.map((item) => {
            const chosen = picked[item.id] ?? [];
            const busy = busyId === item.id;
            return (
              <li key={item.id} className="flex flex-col gap-2 py-3">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-ink-primary">
                    {item.name}
                  </span>
                  {item.vendor ? (
                    <span className="text-sm text-ink-secondary">
                      {item.vendor}
                    </span>
                  ) : null}
                  {item.category ? (
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-ink-secondary">
                      {item.category}
                    </span>
                  ) : null}
                </div>

                {editable ? (
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        run(
                          () => confirmSecurityClassification(item.id),
                          item.id,
                        )
                      }
                      className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
                    >
                      Not security — confirm
                    </button>

                    <span className="text-sm text-ink-secondary">
                      or it is security tooling that:
                    </span>
                    <fieldset className="flex items-center gap-2">
                      <legend className="sr-only">
                        Security functions for {item.name}
                      </legend>
                      {FUNCTIONS.map((fn) => (
                        <label
                          key={fn}
                          className="flex items-center gap-1 text-sm capitalize"
                        >
                          <input
                            type="checkbox"
                            checked={chosen.includes(fn)}
                            onChange={() => toggle(item.id, fn)}
                            disabled={busy}
                          />
                          {fn}s
                        </label>
                      ))}
                    </fieldset>
                    <button
                      type="button"
                      // At least one function: "security-related but serves
                      // none of prevent/detect/respond" is not a claim the
                      // mapping can act on, and the API rejects it.
                      disabled={busy || chosen.length === 0}
                      onClick={() =>
                        run(
                          () => overrideSecurityClassification(item.id, chosen),
                          item.id,
                        )
                      }
                      className="rounded bg-brand-600 px-3 py-1 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                    >
                      Mark security-related
                    </button>
                  </div>
                ) : (
                  <p className="text-sm text-ink-secondary">
                    This list is locked, so its classifications can no longer be
                    changed.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}
