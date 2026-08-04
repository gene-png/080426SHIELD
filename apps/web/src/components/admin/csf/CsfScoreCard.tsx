"use client";
import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  NumberCard,
  StatusPill,
} from "@shield/design-system";

import type { CsfScoreSummary } from "@/lib/csf/types";

import type { JSX } from "react";

export interface CsfScoreCardProps {
  score: CsfScoreSummary | null;
  loading?: boolean;
}

function fmtTier(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(2);
}

function tonelabel(label: string): "info" | "warning" | "success" | "neutral" {
  switch (label) {
    case "Adaptive":
      return "success";
    case "Repeatable":
      return "info";
    case "Risk Informed":
      return "warning";
    case "Partial":
      return "warning";
    default:
      return "neutral";
  }
}

export function CsfScoreCard({
  score,
  loading,
}: CsfScoreCardProps): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Maturity score</CardTitle>
        <CardDescription>
          Average tier is the arithmetic mean of answered subcategories;
          unscored rows are excluded. Coverage shows how complete the assessment
          is.
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        {!score ? (
          <p className="text-sm text-ink-tertiary" aria-live="polite">
            {loading ? "Computing score…" : "No assessment yet."}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill
                tone={tonelabel(score.overall_maturity_label)}
                withDot
              >
                {score.overall_maturity_label}
              </StatusPill>
              <span className="text-xs text-ink-tertiary">
                avg tier {fmtTier(score.average_tier)} · coverage{" "}
                {score.coverage_pct}%
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {score.by_function.map((fs) => (
                <NumberCard
                  key={fs.function}
                  label={`${fs.function} · ${fs.function_name}`}
                  value={fmtTier(fs.average_tier)}
                  hint={`${fs.answered_count}/${fs.subcategory_count} answered · ${fs.coverage_pct}%`}
                />
              ))}
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
