"use client";
import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  NumberCard,
} from "@shield/design-system";

import type { ConsolidationPlanSummary } from "@/lib/tech_debt/types";

import type { JSX } from "react";

export interface ConsolidationPlanCardProps {
  summary: ConsolidationPlanSummary | null;
}

function fmtUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function ConsolidationPlanCard({
  summary,
}: ConsolidationPlanCardProps): JSX.Element | null {
  if (!summary || summary.total_items === 0) return null;

  const savingsLabel = summary.savings_cost_known
    ? fmtUsd(summary.estimated_annual_savings)
    : `≥ ${fmtUsd(summary.estimated_annual_savings)}`;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Consolidation plan</CardTitle>
        <CardDescription>
          Each row in the table above carries a disposition (keep / consolidate
          / cut). The cut-row costs add up to the estimated annual savings shown
          below; the actual deliverable lands in stage 8.
        </CardDescription>
      </CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <NumberCard label="Keep" value={summary.keep_count.toString()} />
          <NumberCard
            label="Consolidate"
            value={summary.consolidate_count.toString()}
          />
          <NumberCard label="Cut" value={summary.cut_count.toString()} />
          <NumberCard
            label="Undecided"
            value={summary.undecided_count.toString()}
            deltaTone={summary.undecided_count === 0 ? "positive" : "negative"}
            delta={
              summary.undecided_count === 0
                ? "All rows decided"
                : "Pick a disposition in the table"
            }
          />
          <NumberCard
            label="Estimated annual savings"
            value={savingsLabel}
            deltaTone="positive"
            hint={
              summary.savings_cost_known
                ? "Sum of annual_cost_usd on cut rows."
                : "At least one cut row is missing a cost; this is a lower bound."
            }
          />
        </div>
      </CardBody>
    </Card>
  );
}
