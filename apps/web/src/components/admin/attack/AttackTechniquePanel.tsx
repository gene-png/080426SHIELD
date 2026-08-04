"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";

import type {
  AttackCoverageRow,
  AttackCoveragePatch,
  CatalogCoverageDefinition,
  CatalogTechnique,
  CoverageStatus,
} from "@/lib/attack/types";

import { StatusBadge } from "./StatusBadge";

import type { JSX } from "react";

const ALL_STATUSES: CoverageStatus[] = [
  "covered",
  "partial",
  "gap",
  "not_applicable",
];

function ToolRow({
  label,
  tools,
}: {
  label: string;
  tools: string[] | null | undefined;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-tertiary">
        {label}
      </span>
      {tools && tools.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {tools.map((t) => (
            <span
              key={t}
              className="rounded-full bg-surface-sunken px-2 py-0.5 text-xs text-ink-secondary"
            >
              {t}
            </span>
          ))}
        </div>
      ) : (
        <span className="text-xs text-ink-tertiary">—</span>
      )}
    </div>
  );
}

export interface AttackTechniquePanelProps {
  technique: CatalogTechnique | null;
  coverage: AttackCoverageRow | null;
  coverageDefinitions: CatalogCoverageDefinition[];
  readOnly?: boolean;
  onPatch: (patch: AttackCoveragePatch) => void | Promise<void>;
}

export function AttackTechniquePanel({
  technique,
  coverage,
  coverageDefinitions,
  readOnly = false,
  onPatch,
}: AttackTechniquePanelProps): JSX.Element {
  if (!technique) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Technique details</CardTitle>
          <CardDescription>
            Select a technique in the matrix to set coverage.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>
            <span className="font-mono text-sm text-ink-tertiary">
              {technique.id}
            </span>{" "}
            · {technique.name}
          </CardTitle>
          <StatusBadge status={coverage?.status ?? null} />
        </div>
        <CardDescription>
          Tactics: {technique.tactics.join(", ")}
          {technique.parent_id ? ` · parent ${technique.parent_id}` : ""}
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        <div
          role="radiogroup"
          aria-label="Coverage status"
          className="flex flex-wrap gap-2"
        >
          {ALL_STATUSES.map((s) => {
            const def = coverageDefinitions.find((d) => d.status === s);
            const active = coverage?.status === s;
            return (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={active}
                disabled={readOnly}
                title={def?.description ?? s}
                onClick={() => void onPatch({ status: active ? null : s })}
                className={[
                  "rounded-md border px-3 py-1.5 text-xs font-semibold transition",
                  active
                    ? "border-brand-500 bg-brand-500 text-ink-on-accent"
                    : "border-border bg-surface-card text-ink-secondary hover:bg-surface-sunken",
                  readOnly ? "cursor-not-allowed opacity-50" : "",
                ].join(" ")}
              >
                {def?.short_label ?? s}
              </button>
            );
          })}
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-tertiary">
            Notes
          </span>
          <textarea
            key={coverage?.id ?? "no-coverage"}
            aria-label={`Notes for ${technique.id}`}
            defaultValue={coverage?.notes ?? ""}
            disabled={readOnly}
            rows={4}
            placeholder="Evidence, controls, detections, exceptions…"
            onBlur={(e) => {
              const v = e.currentTarget.value.trim();
              if (v === (coverage?.notes ?? "")) return;
              void onPatch({ notes: v });
            }}
            className="w-full rounded-md border border-border bg-surface-card p-2 text-sm text-ink-primary focus:border-brand-500 focus:outline-hidden"
          />
        </label>

        <div className="grid grid-cols-1 gap-3 border-t border-border-subtle pt-3 sm:grid-cols-3">
          <ToolRow label="Detection" tools={coverage?.detection_tools} />
          <ToolRow label="Prevention" tools={coverage?.prevention_tools} />
          <ToolRow label="Response" tools={coverage?.response_tools} />
        </div>
        {coverage?.rationale ? (
          <p className="text-sm text-ink-secondary">
            <span className="font-medium text-ink-primary">Rationale: </span>
            {coverage.rationale}
          </p>
        ) : null}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={coverage?.locked ?? false}
            disabled={readOnly || !coverage}
            onChange={(e) => void onPatch({ locked: e.currentTarget.checked })}
          />
          <span className="text-ink-secondary">
            Lock this technique against AI reruns
          </span>
        </label>
      </CardBody>
    </Card>
  );
}
