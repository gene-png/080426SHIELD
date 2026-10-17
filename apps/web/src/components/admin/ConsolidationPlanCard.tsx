"use client";
import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  NumberCard,
} from "@shield/design-system";

import { DISPOSITION_LABEL } from "@/lib/tech_debt/dispositionLabels";
import type { ConsolidationPlanSummary } from "@/lib/tech_debt/types";

import type { JSX } from "react";

import { TD_SECTION_COPY } from "./techDebtSections";

export interface ConsolidationPlanCardProps {
  summary: ConsolidationPlanSummary | null;
  /** #1376: shown in the Analysis section, where the table is not above. */
  inSection?: boolean;
}

function fmtUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function ConsolidationPlanCard({
  summary,
  inSection = false,
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
          {inSection ? (
            TD_SECTION_COPY.planDescription
          ) : (
            <>
              Each row in the table above carries a disposition: Keep, Cut, or
              Cut, covered by another tool. The annual costs of both kinds of
              cut add up to the estimated annual savings shown below. Finalize
              the deliverable when the dispositions are settled.
            </>
          )}
        </CardDescription>
      </CardHeader>
      <CardBody>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <NumberCard label="Keep" value={summary.keep_count.toString()} />
          <NumberCard
            label={DISPOSITION_LABEL.consolidate}
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
                ? "Sum of the annual costs of rows marked Cut or Cut, covered by another tool."
                : "At least one row marked to cut is missing a cost; this is a lower bound."
            }
          />
        </div>
      </CardBody>
    </Card>
  );
}
