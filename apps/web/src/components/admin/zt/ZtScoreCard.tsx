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

import type { ZtScoreSummary } from "@/lib/zt/types";

import type { JSX } from "react";

export interface ZtScoreCardProps {
  score: ZtScoreSummary | null;
  loading?: boolean;
}

function fmtStage(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(2);
}

function toneFor(label: string): "info" | "warning" | "success" | "neutral" {
  if (label === "Optimal") return "success";
  if (label === "Advanced") return "info";
  if (label === "Target" || label === "Initial") return "warning";
  if (label === "Traditional" || label === "Not Started") return "warning";
  return "neutral";
}

export function ZtScoreCard({ score, loading }: ZtScoreCardProps): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Maturity score</CardTitle>
        <CardDescription>
          Average stage is the arithmetic mean of answered capabilities;
          unscored rows are excluded. Coverage reflects how complete the
          assessment is.
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
              <StatusPill tone={toneFor(score.overall_stage_label)} withDot>
                {score.overall_stage_label}
              </StatusPill>
              <span className="text-xs text-ink-tertiary">
                avg stage {fmtStage(score.average_stage)} · coverage{" "}
                {score.coverage_pct}%
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {score.by_pillar.map((ps) => (
                <NumberCard
                  key={ps.pillar_code}
                  label={`${ps.pillar_code} · ${ps.pillar_name}`}
                  value={fmtStage(ps.average_stage)}
                  hint={`${ps.answered_count}/${ps.capability_count} answered · ${ps.coverage_pct}%`}
                />
              ))}
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
