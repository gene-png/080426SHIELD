"use client";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";
import * as React from "react";

import {
  bulkSetDisposition,
  previewSavings,
  proxyMessage,
} from "@/lib/tech_debt/client";
import { DISPOSITION_LABEL } from "@/lib/tech_debt/dispositionLabels";
import type {
  CapabilityDisposition,
  CapabilityList,
  SavingsPreview,
} from "@/lib/tech_debt/types";

import type { JSX } from "react";

/**
 * #804: the Tech Debt savings what-if. The admin ticks tools and sees what the
 * estimated annual savings WOULD be; nothing changes on the plan until "Apply
 * to plan" writes the choices through the disposition route and its guards.
 *
 * The figure is the SERVER's (`/savings-preview`), computed by the same
 * function the deliverable uses, so this panel cannot disagree with the
 * document the same ticks would produce. It is never re-derived here.
 *
 * No AI, no chat, and no ATT&CK coverage figure: Gene decided a live coverage
 * recount would mislead (#802).
 */

const DEBOUNCE_MS = 300;

/** The choices a row offers. "" is "as planned": no proposal for that row. */
const CHOICES: ReadonlyArray<CapabilityDisposition> = [
  "keep",
  "cut",
  "consolidate",
];

const COPY = {
  title: "Savings what-if",
  description:
    "Choose what would happen to each tool and see the estimated annual savings. Nothing changes on the plan until you apply it.",
  asPlanned: (current: string) => `As planned (${current})`,
  undecided: "Undecided",
  current: "On the plan now",
  whatIf: "With these choices",
  lowerBound:
    "At least one tool you would cut has no annual cost, so this figure is a lower bound.",
  apply: "Apply to plan",
  applying: "Applying…",
  reset: "Reset",
  previewFailed: "Couldn't work out the savings for these choices.",
  applyFailed: "Couldn't apply these choices to the plan.",
} as const;

function usd(amount: number, known: boolean): string {
  const text = `$${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  return known ? text : `≥ ${text}`;
}

type Phase =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; preview: SavingsPreview }
  | { kind: "error"; message: string };

export interface SavingsWhatIfProps {
  list: CapabilityList;
  /** The real plan's savings, from the consolidation-plan summary. */
  planSavings: number;
  planKnown: boolean;
  onApplied: (list: CapabilityList) => void;
}

export function SavingsWhatIf({
  list,
  planSavings,
  planKnown,
  onApplied,
}: SavingsWhatIfProps): JSX.Element {
  const [proposed, setProposed] = React.useState<
    Record<string, CapabilityDisposition>
  >({});
  const [result, setResult] = React.useState<{
    key: string;
    phase: Phase;
  } | null>(null);
  const [applying, setApplying] = React.useState(false);
  const [applyError, setApplyError] = React.useState<string | null>(null);

  const changed = Object.keys(proposed).length > 0;
  // Each answer is stored under the choices it was asked for, and the phase
  // shown is DERIVED from whether that matches the choices now. An answer that
  // arrives late, for choices the admin has since changed, can never show.
  const key = JSON.stringify(proposed);
  const phase: Phase = !changed
    ? { kind: "idle" }
    : result?.key === key
      ? result.phase
      : { kind: "loading" };

  React.useEffect(() => {
    if (!changed) return;
    const timer = setTimeout(() => {
      previewSavings(list.id, proposed).then(
        (preview) => setResult({ key, phase: { kind: "ready", preview } }),
        (err: unknown) =>
          setResult({
            key,
            phase: {
              kind: "error",
              message: proxyMessage(err, COPY.previewFailed),
            },
          }),
      );
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [changed, key, list.id, proposed]);

  function choose(itemId: string, value: string): void {
    setApplyError(null);
    setProposed((prev) => {
      const next = { ...prev };
      if (value === "") delete next[itemId];
      else next[itemId] = value as CapabilityDisposition;
      return next;
    });
  }

  async function apply(): Promise<void> {
    setApplying(true);
    setApplyError(null);
    try {
      // One bulk write per chosen disposition, through the route's own guards.
      const groups = new Map<CapabilityDisposition, string[]>();
      for (const [itemId, disposition] of Object.entries(proposed)) {
        groups.set(disposition, [...(groups.get(disposition) ?? []), itemId]);
      }
      let latest: CapabilityList | null = null;
      for (const [disposition, itemIds] of groups) {
        latest = await bulkSetDisposition(list.id, itemIds, disposition);
      }
      setProposed({});
      if (latest) onApplied(latest);
    } catch (err) {
      setApplyError(proxyMessage(err, COPY.applyFailed));
    } finally {
      setApplying(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{COPY.title}</CardTitle>
        <CardDescription>{COPY.description}</CardDescription>
      </CardHeader>
      <CardBody>
        <div className="flex flex-wrap gap-6 text-sm">
          <div>
            <div className="text-ink-tertiary">{COPY.current}</div>
            <div
              className="text-lg font-semibold text-ink-primary"
              data-testid="what-if-current"
            >
              {usd(planSavings, planKnown)}
            </div>
          </div>
          {phase.kind === "ready" ? (
            <div>
              <div className="text-ink-tertiary">{COPY.whatIf}</div>
              <div
                className="text-lg font-semibold text-ink-primary"
                data-testid="what-if-savings"
              >
                {usd(
                  phase.preview.estimated_annual_savings,
                  phase.preview.savings_cost_known,
                )}
              </div>
            </div>
          ) : null}
        </div>
        {phase.kind === "ready" && !phase.preview.savings_cost_known ? (
          <p
            className="mt-2 text-sm text-ink-secondary"
            data-testid="what-if-savings-note"
          >
            {COPY.lowerBound}
          </p>
        ) : null}
        {phase.kind === "error" ? (
          <p role="alert" className="mt-2 text-sm text-danger-600">
            {phase.message}
          </p>
        ) : null}

        <table className="mt-4 w-full text-left text-sm">
          <tbody>
            {list.items
              .filter((it) => !it.parent_item_id)
              .map((it) => {
                const current = it.disposition
                  ? DISPOSITION_LABEL[it.disposition]
                  : COPY.undecided;
                return (
                  <tr key={it.id} className="border-b border-border-subtle">
                    <td className="py-1 pr-3 text-ink-primary">{it.name}</td>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {it.annual_cost_usd === null ||
                      it.annual_cost_usd === undefined
                        ? "—"
                        : usd(Number(it.annual_cost_usd), true)}
                    </td>
                    <td className="py-1">
                      <select
                        aria-label={`What-if for ${it.name}`}
                        value={proposed[it.id] ?? ""}
                        onChange={(e) => choose(it.id, e.target.value)}
                        className="rounded border border-border-subtle bg-surface-raised px-2 py-1"
                      >
                        <option value="">{COPY.asPlanned(current)}</option>
                        {CHOICES.map((c) => (
                          <option key={c} value={c}>
                            {DISPOSITION_LABEL[c]}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>

        {applyError ? (
          <p role="alert" className="mt-2 text-sm text-danger-600">
            {applyError}
          </p>
        ) : null}
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void apply()}
            disabled={!changed || applying}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {applying ? COPY.applying : COPY.apply}
          </button>
          <button
            type="button"
            onClick={() => setProposed({})}
            disabled={!changed || applying}
            className="rounded-md border border-border-subtle px-4 py-2 text-sm text-ink-primary hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-60"
          >
            {COPY.reset}
          </button>
        </div>
      </CardBody>
    </Card>
  );
}
