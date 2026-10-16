"use client";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import {
  bulkConfirmSecurityClassification,
  confirmSecurityClassification,
  overrideSecurityClassification,
} from "@/lib/tech_debt/client";
import type {
  CapabilityItem,
  CapabilityList,
  SecurityFunction,
} from "@/lib/tech_debt/types";

import { useRowSelection } from "./useRowSelection";
import type { RowSelection } from "./useRowSelection";

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

/**
 * #845: a security tool the extraction marked "Security tool not in use:" (Tech
 * Debt v3.2). The API decides (`security_scope.signoff_kind`); this only reads
 * it, so the screen and the audit cannot disagree. Absent reads as the ordinary
 * wording, the fallback the plan states.
 */
function notInUse(item: CapabilityItem): boolean {
  return item.signoff_kind === "not_in_use";
}

/* #1174: the bulk confirm's labels, approved on #736 (6206818759 item 7). */
const SELECT_ALL = (n: number) => `Select all (${n})`;
const BULK_NOT_IN_USE = (k: number) =>
  k === 1
    ? "Not in use: remove 1 from ATT&CK"
    : `Not in use: remove ${k} from ATT&CK`;
const BULK_NOT_SECURITY = (k: number) =>
  k === 1 ? "Not security: confirm 1" : `Not security: confirm ${k}`;

/* Copy approved on #845 (issue 845 comment 5983735296; 736 comment 5986057990). */
const Q1 = (n: number) => `Security tools not in use (${n})`;
const Q2 =
  "The AI found these security tools described as planned, not yet deployed, inactive or no longer used. Until you confirm, they stay in the ATT&CK tool mapping, where they can be credited as if deployed.";
const Q3 = "Not in use: remove from ATT&CK";
const Q4 =
  "If the tool is in use, mark it security-related: it stays in the ATT&CK assessment.";
const Q5 = "Marking it security-related keeps it in the ATT&CK assessment.";
const Q7 =
  "Clear this queue before you approve the list. If the list is already approved, choose Approve again after confirming, then use Run AI on the ATT&CK service so its mapping stops crediting these tools.";

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
  const notInUseRows = pending.filter(notInUse);
  const notSecurityRows = pending.filter((i) => !notInUse(i));
  const contradictions = list.not_in_use_contradictions ?? 0;
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [picked, setPicked] = React.useState<
    Record<string, SecurityFunction[]>
  >({});
  // #1174: "select all, then untick the exceptions", one selection per card.
  const notInUseSel = useRowSelection(notInUseRows.map((i) => i.id));
  const notSecuritySel = useRowSelection(notSecurityRows.map((i) => i.id));

  if (pending.length === 0 && contradictions === 0) return null;

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

  /**
   * #1174: a card's select-all and its bulk confirm. The bulk call sends
   * exactly the ticked rows; the server refuses the whole request if any of
   * them no longer needs sign-off, and `run` shows that refusal.
   */
  function bulkBar(n: number, sel: RowSelection, label: (k: number) => string) {
    const k = sel.selected.length;
    return (
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={sel.allSelected}
            onChange={sel.toggleAll}
            disabled={busyId !== null}
          />
          {SELECT_ALL(n)}
        </label>
        <button
          type="button"
          disabled={k === 0 || busyId !== null}
          onClick={() =>
            run(
              () => bulkConfirmSecurityClassification(list.id, sel.selected),
              "bulk",
            )
          }
          className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {label(k)}
        </button>
      </div>
    );
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

  function row(
    item: CapabilityItem,
    kind: "not_in_use" | "not_security",
    sel: RowSelection,
  ) {
    const chosen = picked[item.id] ?? [];
    // #1174: ANY run in flight (a row's, or the bulk confirm) disables every
    // row's controls, so a single confirm cannot race a bulk one.
    const busy = busyId !== null;
    return (
      <li key={item.id} className="flex flex-col gap-2 py-3">
        <div className="flex flex-wrap items-baseline gap-2">
          {editable ? (
            <input
              type="checkbox"
              checked={sel.isSelected(item.id)}
              onChange={() => sel.toggle(item.id)}
              disabled={busyId !== null}
              aria-label={`Select ${item.name}`}
            />
          ) : null}
          <span className="font-medium text-ink-primary">{item.name}</span>
          {item.vendor ? (
            <span className="text-sm text-ink-secondary">{item.vendor}</span>
          ) : null}
          {item.category ? (
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-ink-secondary">
              {item.category}
            </span>
          ) : null}
        </div>
        {item.notes ? (
          <p
            className="text-sm text-ink-secondary"
            data-testid="security-signoff-note"
          >
            Note: {item.notes}
          </p>
        ) : null}

        {editable ? (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  run(() => confirmSecurityClassification(item.id), item.id)
                }
                className="rounded border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
              >
                {kind === "not_in_use" ? Q3 : "Not security — confirm"}
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
            <p className="text-sm text-ink-secondary">
              {kind === "not_in_use" ? Q4 : Q5}
            </p>
          </>
        ) : (
          <p className="text-sm text-ink-secondary">
            This list is locked, so its classifications can no longer be
            changed.
          </p>
        )}
      </li>
    );
  }

  return (
    <>
      {contradictions > 0 ? (
        <p
          className="text-sm text-ink-secondary"
          data-testid="security-signoff-contradictions"
        >
          {contradictions === 1
            ? "1 tool was described as not in use but also given security functions, so it stays in the ATT&CK assessment."
            : `${contradictions} tools were described as not in use but also given security functions, so they stay in the ATT&CK assessment.`}
        </p>
      ) : null}

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

      {notInUseRows.length > 0 ? (
        <Card data-testid="security-signoff-not-in-use">
          <CardHeader>
            <CardTitle>{Q1(notInUseRows.length)}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            <p className="max-w-prose text-sm text-ink-secondary">{Q2}</p>
            {editable
              ? bulkBar(notInUseRows.length, notInUseSel, BULK_NOT_IN_USE)
              : null}
            <ul className="divide-y divide-slate-200">
              {notInUseRows.map((item) => row(item, "not_in_use", notInUseSel))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {notSecurityRows.length > 0 ? (
        <Card data-testid="security-signoff-not-security">
          <CardHeader>
            <CardTitle>
              Confirm security classification ({notSecurityRows.length})
            </CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            <p className="max-w-prose text-sm text-ink-secondary">
              The AI classified these as <strong>not security-related</strong>.
              Until you agree, they stay in the ATT&amp;CK tool mapping — a
              security tool dropped by mistake cannot be cited there at all, and
              its absence would read as a coverage gap rather than a missing
              input.
            </p>
            {editable
              ? bulkBar(
                  notSecurityRows.length,
                  notSecuritySel,
                  BULK_NOT_SECURITY,
                )
              : null}
            <ul className="divide-y divide-slate-200">
              {notSecurityRows.map((item) =>
                row(item, "not_security", notSecuritySel),
              )}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {/* Only where the controls it names exist: a locked (released) list
          offers neither the sign-off buttons nor approval (D-076). */}
      {pending.length > 0 && editable ? (
        <p
          className="max-w-prose text-sm text-ink-secondary"
          data-testid="security-signoff-procedure"
        >
          {Q7}
        </p>
      ) : null}
    </>
  );
}
