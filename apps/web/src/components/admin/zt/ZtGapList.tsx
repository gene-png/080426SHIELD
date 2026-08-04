"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  StatusPill,
} from "@shield/design-system";

import type { CatalogStage, GapAnalysis } from "@/lib/zt/types";

import type { JSX } from "react";

export interface ZtGapListProps {
  analysis: GapAnalysis | null;
  loading?: boolean;
  targetStage: number;
  onChangeTargetStage: (next: number) => void;
  stages: CatalogStage[];
}

function severityTone(gapSize: number): "warning" | "info" | "success" {
  if (gapSize >= 2) return "warning";
  if (gapSize >= 1) return "info";
  return "success";
}

export function ZtGapList({
  analysis,
  loading,
  targetStage,
  onChangeTargetStage,
  stages,
}: ZtGapListProps): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Remediation gaps</CardTitle>
        <CardDescription>
          Capabilities whose current stage is below the target. Priority weights
          Identity + Data slightly higher because they sit closest to protected
          resources.
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2 text-ink-secondary">
            Target stage
            <select
              value={targetStage}
              onChange={(e) =>
                onChangeTargetStage(Number(e.currentTarget.value))
              }
              className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
            >
              {stages
                .filter((s) => s.stage >= 2)
                .map((s) => (
                  <option key={s.stage} value={s.stage}>
                    {s.stage} · {s.label}
                  </option>
                ))}
            </select>
          </label>
          {analysis ? (
            <span className="text-xs text-ink-tertiary">
              {analysis.total_gap_count} gap
              {analysis.total_gap_count === 1 ? "" : "s"} ·{" "}
              {analysis.unscored_count} unscored
            </span>
          ) : null}
        </div>

        {!analysis ? (
          <p className="text-sm text-ink-tertiary" aria-live="polite">
            {loading ? "Loading gaps…" : "No assessment yet."}
          </p>
        ) : analysis.gaps.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            No gaps at target stage {analysis.target_stage} (
            {analysis.target_label}). Raise the target or score more
            capabilities to surface gaps.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {analysis.gaps.map((g) => (
              <li
                key={g.code}
                className="rounded-md border border-border-subtle bg-surface-card p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-mono text-ink-tertiary">
                      {g.code} · {g.pillar_name}
                    </p>
                    <p className="text-sm font-medium text-ink-primary">
                      {g.name}
                    </p>
                    <p className="mt-1 text-sm text-ink-secondary">
                      {g.outcome}
                    </p>
                    {g.notes ? (
                      <p className="mt-1 text-xs italic text-ink-tertiary">
                        Notes: {g.notes}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-col items-end gap-1 text-right">
                    <StatusPill tone={severityTone(g.gap_size)}>
                      gap {g.gap_size}
                    </StatusPill>
                    <span className="text-xs text-ink-tertiary">
                      S{g.current_stage} → S{g.target_stage}
                    </span>
                    <span className="text-xs text-ink-tertiary">
                      priority {g.priority_score.toFixed(2)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
