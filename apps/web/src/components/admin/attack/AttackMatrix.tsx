"use client";
import * as React from "react";

import type {
  AttackCatalog,
  AttackCoverageRow,
  CatalogTechnique,
  TacticHeatmapEntry,
} from "@/lib/attack/types";

import { StatusBadge } from "./StatusBadge";

import type { JSX } from "react";

export interface AttackMatrixProps {
  catalog: AttackCatalog;
  coverageByCode: Record<string, AttackCoverageRow>;
  heatmapByTactic: Record<string, TacticHeatmapEntry>;
  onSelectTechnique: (code: string) => void;
  selectedCode: string | null;
  showSubTechniques: boolean;
  onToggleSubTechniques: (next: boolean) => void;
}

interface ColumnBuckets {
  tactic_id: string;
  tactic_name: string;
  parents: CatalogTechnique[];
  subs: CatalogTechnique[];
}

function buildColumns(catalog: AttackCatalog): ColumnBuckets[] {
  return catalog.tactics.map((t) => {
    const parents: CatalogTechnique[] = [];
    const subs: CatalogTechnique[] = [];
    for (const tech of catalog.techniques) {
      if (!tech.tactics.includes(t.id)) continue;
      if (tech.is_sub_technique) {
        subs.push(tech);
      } else {
        parents.push(tech);
      }
    }
    parents.sort((a, b) => a.id.localeCompare(b.id));
    subs.sort((a, b) => a.id.localeCompare(b.id));
    return {
      tactic_id: t.id,
      tactic_name: t.name,
      parents,
      subs,
    };
  });
}

export function AttackMatrix({
  catalog,
  coverageByCode,
  heatmapByTactic,
  onSelectTechnique,
  selectedCode,
  showSubTechniques,
  onToggleSubTechniques,
}: AttackMatrixProps): JSX.Element {
  const columns = React.useMemo(() => buildColumns(catalog), [catalog]);

  return (
    <section
      aria-labelledby="attack-matrix-heading"
      className="flex flex-col gap-3"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2
          id="attack-matrix-heading"
          className="text-lg font-semibold text-ink-primary"
        >
          ATT&amp;CK matrix
        </h2>
        <label className="flex items-center gap-2 text-xs text-ink-secondary">
          <input
            type="checkbox"
            checked={showSubTechniques}
            onChange={(e) => onToggleSubTechniques(e.currentTarget.checked)}
            className="h-3.5 w-3.5"
          />
          Show sub-techniques
        </label>
      </header>
      <p className="text-xs text-ink-tertiary">
        Click any technique cell to set its coverage status + notes in the side
        panel. Cells show the current status; greyed cells are unscored.
      </p>
      <div className="overflow-x-auto rounded-md border border-border-subtle">
        <table className="min-w-full border-collapse text-xs">
          <thead>
            <tr className="bg-surface-sunken">
              {columns.map((col) => {
                const hm = heatmapByTactic[col.tactic_id];
                return (
                  <th
                    key={col.tactic_id}
                    scope="col"
                    className="min-w-[150px] border-b border-border-subtle px-2 py-2 text-left align-bottom"
                  >
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-secondary">
                      {col.tactic_name}
                    </div>
                    <div className="text-[10px] text-ink-tertiary">
                      {col.parents.length} techniques
                    </div>
                    {hm ? (
                      <div className="text-[10px] text-ink-tertiary">
                        cov {hm.coverage_pct}%
                      </div>
                    ) : null}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            <tr className="align-top">
              {columns.map((col) => {
                const rows = showSubTechniques
                  ? [...col.parents, ...col.subs]
                  : col.parents;
                return (
                  <td
                    key={col.tactic_id}
                    className="border-r border-border-subtle px-1 py-1"
                  >
                    <ul className="flex flex-col gap-0.5">
                      {rows.map((tech) => {
                        const cov = coverageByCode[tech.id];
                        const selected = selectedCode === tech.id;
                        return (
                          <li key={tech.id}>
                            <button
                              type="button"
                              onClick={() => onSelectTechnique(tech.id)}
                              className={[
                                "flex w-full items-center gap-1.5 rounded-md border px-1.5 py-1 text-left transition",
                                selected
                                  ? "border-brand-500 bg-brand-50 text-ink-primary"
                                  : "border-border-subtle bg-surface-card hover:bg-surface-sunken",
                                tech.is_sub_technique
                                  ? "ml-3 text-[10px]"
                                  : "text-[11px]",
                              ].join(" ")}
                            >
                              <StatusBadge status={cov?.status ?? null} />
                              <span className="flex flex-col">
                                <span className="font-mono text-[10px] text-ink-tertiary">
                                  {tech.id}
                                </span>
                                <span className="font-medium text-ink-primary">
                                  {tech.name}
                                </span>
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
