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

import type { AttackHeatmap } from "@/lib/attack/types";

import type { JSX } from "react";

export interface AttackHeatmapCardProps {
  heatmap: AttackHeatmap | null;
  loading?: boolean;
}

function toneFor(pct: number): "success" | "info" | "warning" | "neutral" {
  if (pct >= 75) return "success";
  if (pct >= 50) return "info";
  if (pct > 0) return "warning";
  return "neutral";
}

export function AttackHeatmapCard({
  heatmap,
  loading,
}: AttackHeatmapCardProps): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Coverage rollup</CardTitle>
        <CardDescription>
          Coverage % = (covered + 0.5 × partial) / addressable × 100, where
          addressable excludes N/A rows. Per-tactic counts feed the matrix
          below.
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        {!heatmap ? (
          <p className="text-sm text-ink-tertiary" aria-live="polite">
            {loading ? "Computing coverage…" : "No assessment yet."}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill tone={toneFor(heatmap.coverage_pct)} withDot>
                Coverage {heatmap.coverage_pct}%
              </StatusPill>
              <span className="text-xs text-ink-tertiary">
                {heatmap.scored_count}/
                {heatmap.scored_count + heatmap.unscored_count} scored
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <NumberCard
                label="Covered"
                value={heatmap.covered.toString()}
                deltaTone="positive"
              />
              <NumberCard
                label="Partial"
                value={heatmap.partial.toString()}
                deltaTone="positive"
              />
              <NumberCard
                label="Gap"
                value={heatmap.gap.toString()}
                deltaTone={heatmap.gap === 0 ? "positive" : "negative"}
              />
              <NumberCard
                label="N/A"
                value={heatmap.not_applicable.toString()}
                hint="Out of scope for this environment."
              />
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
