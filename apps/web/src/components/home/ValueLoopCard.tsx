import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import type { JSX } from "react";

/**
 * Wire type for GET /clients/{cid}/value-summary
 * (apps/api/app/schemas/clients.py:ValueSummaryResponse).
 *
 * A null slot carries TWO different facts and needs its companion flag to tell
 * them apart (#114 review):
 *
 *   * `<kind>_unresolved === false` — the service has no RELEASED deliverable
 *     yet. Genuinely PENDING, and the card says so.
 *   * `<kind>_unresolved === true`  — the client HAS a released report of that
 *     kind, and it cannot be matched to the assessment behind it. Rendering
 *     that as "Pending" tells a client who has a report that they do not.
 *
 * Never a fabricated 0 in either case.
 */
export interface ValueSummary {
  tech_debt_savings_usd: number | null;
  tech_debt_savings_cost_known: boolean;
  tech_debt_savings_unresolved: boolean;
  zt_gap_count: number | null;
  zt_gap_unresolved: boolean;
  attack_uncovered_count: number | null;
  attack_uncovered_unresolved: boolean;
  csf_gap_count: number | null;
  csf_gap_unresolved: boolean;
  has_any_data: boolean;
  has_unresolved: boolean;
}

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const COUNT = new Intl.NumberFormat("en-US");

interface Metric {
  label: string;
  value: string | null; // null -> "Pending", unless `unresolved`
  hint: string;
  /** The figure could not be resolved for a report the client HAS. Renders the
   *  third state instead of "Pending" — see `ValueSummary`. */
  unresolved: boolean;
  /** What the figure is computed OVER, plural, in the client's words.
   *
   *  Load-bearing for the unresolved copy rather than decoration. The state is
   *  per KIND and wholesale — `_KindTotal`'s docstring says "A kind goes
   *  unresolved WHOLESALE rather than per service", and each `_*_total` returns
   *  on the FIRST unresolvable service — so a sentence saying "this service"
   *  is false whenever the client has more than one. Zero Trust is the sharp
   *  case: `zt_ids` concatenates ZERO_TRUST_CISA and ZERO_TRUST_DOD, so one
   *  slot can span two frameworks and any number of engagements. */
  kindNoun: string;
}

function pluralGaps(n: number): string {
  return n === 1 ? "1 gap to close" : `${COUNT.format(n)} gaps to close`;
}

function buildMetrics(summary: ValueSummary): Metric[] {
  const savings = summary.tech_debt_savings_usd;
  return [
    {
      label: "Tech debt savings identified",
      kindNoun: "software-portfolio reports",
      value:
        savings === null
          ? null
          : summary.tech_debt_savings_cost_known
            ? `${USD.format(savings)} / yr`
            : `${USD.format(savings)}+ / yr`,
      hint:
        savings !== null && !summary.tech_debt_savings_cost_known
          ? "A floor — some retired tools had no cost on file."
          : "Annual spend on tooling marked for consolidation.",
      unresolved: summary.tech_debt_savings_unresolved,
    },
    {
      label: "Zero Trust",
      kindNoun: "Zero Trust reports",
      value:
        summary.zt_gap_count === null ? null : pluralGaps(summary.zt_gap_count),
      hint: "Capabilities below your target maturity stage.",
      unresolved: summary.zt_gap_unresolved,
    },
    {
      label: "MITRE ATT&CK",
      kindNoun: "MITRE ATT&CK reports",
      value:
        summary.attack_uncovered_count === null
          ? null
          : summary.attack_uncovered_count === 1
            ? "1 technique uncovered"
            : `${COUNT.format(summary.attack_uncovered_count)} techniques uncovered`,
      hint: "Adversary techniques with no defensive coverage yet.",
      unresolved: summary.attack_uncovered_unresolved,
    },
    {
      label: "NIST CSF 2.0",
      kindNoun: "NIST CSF reports",
      value:
        summary.csf_gap_count === null
          ? null
          : pluralGaps(summary.csf_gap_count),
      hint: "Subcategories below your target maturity tier.",
      unresolved: summary.csf_gap_unresolved,
    },
  ];
}

/**
 * Cross-service executive value loop (Master Spec §2.5). A single card that
 * synthesizes the deterministic outputs of all four services into one
 * "here's the value delivered" summary. The numbers are computed server-side
 * by the pure engines (GET /clients/{cid}/value-summary) — "AI suggests, code
 * computes." Only released services feed a number (§12); everything else reads
 * "Pending", so the loop visibly fills in as the engagement progresses.
 *
 * Rendered when at least one service has released data OR any figure could not
 * be resolved — a brand-new client sees the /home guidance state instead of a
 * card of blanks. `has_unresolved` is in that condition deliberately: a client
 * with released reports and no resolvable figures has `has_any_data === false`,
 * and gating on that alone made the card vanish with nothing in its place.
 */
export function ValueLoopCard({
  summary,
}: {
  summary: ValueSummary;
}): JSX.Element | null {
  if (!summary.has_any_data && !summary.has_unresolved) return null;
  const metrics = buildMetrics(summary);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your engagement at a glance</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="mb-4 max-w-prose text-sm text-ink-secondary">
          The value your analyst has surfaced across every service, updated as
          each report is released.
        </p>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map((m) => (
            <div
              key={m.label}
              className="rounded-lg border border-border bg-surface-sunken px-4 py-3"
            >
              <dt className="text-xs font-medium text-ink-secondary">
                {m.label}
              </dt>
              <dd className="mt-1 text-lg font-semibold text-ink-primary">
                {/* THE FLAG DECIDES, NOT THE VALUE, and the order matters.
                    This read `m.value ?? (m.unresolved ? …)`, so a response
                    carrying BOTH a value and the flag rendered the number while
                    the hint below — which switches on `m.unresolved` alone —
                    said we were not showing one. No backend path produces that
                    pair today (every unresolved `_KindTotal` carries `None`),
                    but "unreachable because the server is well-behaved" is a
                    guarantee held in another file, and this ordering makes the
                    renderer honest without depending on it. */}
                {m.unresolved ? (
                  <span className="text-base font-normal text-status-warning-fg">
                    Not available
                  </span>
                ) : (
                  (m.value ?? (
                    <span className="text-base font-normal text-ink-tertiary">
                      Pending
                    </span>
                  ))
                )}
              </dd>
              <p className="mt-1 text-xs text-ink-tertiary">
                {m.unresolved
                  ? `We can't match this figure to your ${m.kindNoun}, so we're not showing a number — including for any of them that are fine. They are still available under Results. Your analyst will need to look into it.`
                  : m.hint}
              </p>
            </div>
          ))}
        </dl>
      </CardBody>
    </Card>
  );
}
