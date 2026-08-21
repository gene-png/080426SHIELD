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
          addressable excludes N/A rows and rows pending review — a technique
          whose supporting citation is unconfirmed withholds its claim rather
          than scoring as covered or as a gap. Per-tactic counts feed the matrix
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
              {/*
                #102. Rendered BESIDE the percentage and never instead of it.
                Coverage % is a ratio over the techniques that can currently be
                claimed, so withholding a row leaves both the numerator and the
                denominator -- the percentage on its own does not say how much of
                the assessment it is a percentage OF. Suppressed at zero on
                purpose: a permanent "0 pending review" trains the eye to skip
                the line, which is how the number stops being read on the run
                where it is not zero.
              */}
              {(heatmap.pending_review ?? 0) > 0 ? (
                <StatusPill tone="warning" withDot>
                  <span data-testid="attack-heatmap-pending">
                    {heatmap.pending_review} pending review
                  </span>
                </StatusPill>
              ) : null}
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
              <NumberCard
                label="Pending review"
                value={(heatmap.pending_review ?? 0).toString()}
                deltaTone={
                  (heatmap.pending_review ?? 0) === 0 ? "positive" : "negative"
                }
                hint="A status was assigned but its supporting citation is unconfirmed. Held out of the coverage score until someone confirms it — not a gap."
              />
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
