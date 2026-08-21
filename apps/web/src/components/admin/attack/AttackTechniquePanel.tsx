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
  UnconfirmedCitation,
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

/**
 * How one citation outcome reads to a consultant. `cited` is what the model
 * actually wrote and is the part they act on -- "Qradar" tells them the approved
 * list holds something else, where the resolved name tells them nothing about
 * why the citation needed rescuing.
 */
function citationLine(c: UnconfirmedCitation): string {
  if (c.reason === "no_citation") {
    return "The model claimed this status and cited no tool at all.";
  }
  if (c.tool === null) {
    return `Cited "${c.cited ?? "\u2014"}" \u2014 not on the approved list, so nothing was applied.`;
  }
  return `Cited "${c.cited ?? c.tool}" \u2014 resolved to ${c.tool} (${c.reason.replace(/_/g, " ")}).`;
}

export interface AttackTechniquePanelProps {
  technique: CatalogTechnique | null;
  coverage: AttackCoverageRow | null;
  coverageDefinitions: CatalogCoverageDefinition[];
  readOnly?: boolean;
  onPatch: (patch: AttackCoveragePatch) => void | Promise<void>;
  /**
   * #101 / #102. Vouch for every outstanding citation on this row so its status
   * may score again. Distinct from `onPatch` deliberately: this says "the
   * resolver got it right", a status edit says "here is my own answer", and both
   * make the row score.
   */
  onConfirmCitations?: () => void | Promise<void>;
}

export function AttackTechniquePanel({
  technique,
  coverage,
  coverageDefinitions,
  readOnly = false,
  onPatch,
  onConfirmCitations,
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

  // Cleared entries are rendered too, not just outstanding ones: "a human
  // accepted this" and "nobody ever cited it" are different answers to why this
  // technique counts, and this panel is where that question gets asked.
  const citations = coverage?.unconfirmed_citations ?? [];
  const outstanding = citations.filter(
    (c) => (c.cleared_at ?? null) === null,
  ).length;
  // A row is ALSO withheld when `unconfirmed_citations` is null — the
  // pre-resolver state, where nobody ever checked this row's citations. There
  // is nothing to list and nothing to confirm, so gating the whole block on
  // `citations.length` left a red badge over an empty panel with no route out.
  // Reachable today: a locked row in a draft assessment is skipped by Run-AI,
  // skipped by migration 0045, and 409s on confirm-citations.
  const pendingWithoutRecord =
    (coverage?.pending_review ?? false) && citations.length === 0;

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
          <StatusBadge
            status={coverage?.status ?? null}
            pendingReview={coverage?.pending_review ?? false}
          />
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
        {citations.length > 0 || pendingWithoutRecord ? (
          <div
            className="flex flex-col gap-2 rounded-md border border-dashed border-border p-3"
            data-testid="attack-citation-queue"
          >
            <span className="text-xs font-medium uppercase tracking-wide text-ink-tertiary">
              Citation review
            </span>
            {pendingWithoutRecord ? (
              <p className="text-sm text-ink-secondary">
                This technique&rsquo;s citations were{" "}
                <span className="font-medium text-status-info-fg">
                  never resolved
                </span>{" "}
                &mdash; it predates the citation resolver, so nothing on record
                says what its evidence was checked against. It is held out of
                the coverage score until someone vouches for it, and it is not a
                gap. There is nothing stored to confirm here: set the status or
                the tools yourself to take authorship of the claim.
              </p>
            ) : null}
            <ul className="flex flex-col gap-1 text-sm text-ink-secondary">
              {citations.map((c, i) => (
                <li
                  key={`${c.tool ?? "none"}-${c.cited ?? i}-${c.field ?? ""}`}
                >
                  {citationLine(c)}{" "}
                  {(c.cleared_at ?? null) === null ? (
                    <span className="font-medium text-status-info-fg">
                      Awaiting review.
                    </span>
                  ) : (
                    <span className="font-medium text-status-success-fg">
                      Confirmed by a reviewer.
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {outstanding > 0 ? (
              <p className="text-xs text-ink-tertiary">
                While anything here is awaiting review and nothing else on this
                technique is confirmed, the coverage score holds this status
                back \u2014 it is not counted as covered, and it is not a gap.
              </p>
            ) : null}
            {outstanding > 0 && !readOnly && onConfirmCitations ? (
              <button
                type="button"
                onClick={() => void onConfirmCitations()}
                className="self-start rounded-md border border-border bg-surface-card px-2 py-1 text-xs font-medium text-ink-primary hover:bg-surface-sunken focus:outline-2 focus:outline-brand-500"
              >
                Confirm this evidence
              </button>
            ) : null}
          </div>
        ) : null}

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
