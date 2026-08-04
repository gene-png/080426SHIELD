"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";

import type { GapAnalysis, RoadmapEntry } from "@/lib/zt/types";

import type { JSX } from "react";

export interface ZtRoadmapCardProps {
  analysis: GapAnalysis | null;
}

export function ZtRoadmapCard({
  analysis,
}: ZtRoadmapCardProps): JSX.Element | null {
  const byMonth = React.useMemo(() => {
    const map = new Map<number, RoadmapEntry[]>();
    for (const r of analysis?.roadmap ?? []) {
      const list = map.get(r.month) ?? [];
      list.push(r);
      map.set(r.month, list);
    }
    return map;
  }, [analysis]);

  if (!analysis) return null;
  const roadmap = analysis.roadmap ?? [];
  const months = [...byMonth.keys()].sort((a, b) => a - b);

  return (
    <Card>
      <CardHeader>
        <CardTitle>12-month roadmap</CardTitle>
        <CardDescription>
          Prioritized gaps sequenced across a year — Identity/User and Data
          weigh heavier, so they land in earlier months.
        </CardDescription>
      </CardHeader>
      <CardBody>
        {roadmap.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            No gaps to sequence — every scored capability meets its target.
          </p>
        ) : (
          <ol className="flex flex-col gap-4">
            {months.map((m) => (
              <li key={m} className="flex flex-col gap-1">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
                  Month {m}
                </h4>
                <ul className="flex flex-col gap-1">
                  {(byMonth.get(m) ?? []).map((r) => (
                    <li
                      key={r.code}
                      className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-border-subtle px-3 py-1.5"
                    >
                      <span className="text-sm text-ink-primary">
                        <span className="font-medium">{r.code}</span> {r.name}
                      </span>
                      <span className="text-xs text-ink-secondary">
                        {r.pillar_name} · L{r.current_stage} → L{r.target_stage}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        )}
      </CardBody>
    </Card>
  );
}
