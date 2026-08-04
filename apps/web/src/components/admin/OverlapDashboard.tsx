"use client";
import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  NumberCard,
  StatusPill,
} from "@shield/design-system";

import type { OverlapAnalysis, OverlapBucket } from "@/lib/tech_debt/types";

import type { JSX } from "react";

export interface OverlapDashboardProps {
  analysis: OverlapAnalysis | null;
  loading?: boolean;
  error?: string | null;
}

function fmtUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function BucketList({
  buckets,
  emptyMessage,
}: {
  buckets: OverlapBucket[];
  emptyMessage: string;
}): JSX.Element {
  if (buckets.length === 0) {
    return <p className="text-sm italic text-ink-tertiary">{emptyMessage}</p>;
  }
  return (
    <ul className="flex flex-col gap-3">
      {buckets.map((b) => (
        <li
          key={b.key}
          className="rounded-md border border-border-subtle bg-surface-card p-3"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-semibold text-ink-primary">{b.key}</p>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill tone="warning">
                {b.item_count} overlapping items
              </StatusPill>
              <StatusPill tone="neutral">
                {b.cost_known
                  ? fmtUsd(b.total_cost)
                  : `≥ ${fmtUsd(b.total_cost)}`}
              </StatusPill>
            </div>
          </div>
          <p className="mt-2 text-xs text-ink-secondary">
            {b.item_names.join(" · ")}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function OverlapDashboard({
  analysis,
  loading = false,
  error = null,
}: OverlapDashboardProps): JSX.Element {
  if (loading) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-ink-tertiary">
            Computing overlap analysis…
          </p>
        </CardBody>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Couldn&apos;t compute overlap</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-status-danger-fg">{error}</p>
        </CardBody>
      </Card>
    );
  }
  if (!analysis || analysis.total_items === 0) {
    return (
      <EmptyState
        title="No overlap analysis yet"
        description="Once a capability list has been extracted, this dashboard shows category and vendor overlaps + top-cost items."
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink-primary">
            Overlap analysis
          </h2>
          <p className="text-sm text-ink-secondary">
            Categories and vendors that show up more than once — consolidation
            candidates. Includes top-cost items so the conversation can start
            with the biggest line items.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <NumberCard
          label="Total annual cost"
          value={fmtUsd(analysis.total_cost)}
        />
        <NumberCard
          label="Items in list"
          value={analysis.total_items.toString()}
        />
        <NumberCard
          label="Missing category"
          value={analysis.uncategorized_count.toString()}
          deltaTone={
            analysis.uncategorized_count === 0 ? "positive" : "negative"
          }
          delta={
            analysis.uncategorized_count === 0
              ? "All rows categorized"
              : "Edit rows in the table"
          }
        />
        <NumberCard
          label="Missing cost"
          value={analysis.no_cost_count.toString()}
          deltaTone={analysis.no_cost_count === 0 ? "positive" : "negative"}
          delta={
            analysis.no_cost_count === 0
              ? "All rows costed"
              : "Annual cost informs the plan"
          }
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Overlap by category</CardTitle>
            <CardDescription>
              Tools serving the same security function — strong consolidation
              candidates.
            </CardDescription>
          </CardHeader>
          <CardBody>
            <BucketList
              buckets={analysis.by_category}
              emptyMessage="No categories with more than one item."
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Overlap by vendor</CardTitle>
            <CardDescription>
              Multiple subscriptions from one vendor — volume / consolidation
              negotiation targets.
            </CardDescription>
          </CardHeader>
          <CardBody>
            <BucketList
              buckets={analysis.by_vendor}
              emptyMessage="No vendor repeats."
            />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Top-cost items</CardTitle>
          <CardDescription>
            The five largest line items in the current list. Start the
            consolidation conversation here.
          </CardDescription>
        </CardHeader>
        <CardBody>
          {analysis.top_cost_items.length === 0 ? (
            <p className="text-sm italic text-ink-tertiary">
              No items have a cost on file yet.
            </p>
          ) : (
            <ol className="flex flex-col gap-1">
              {analysis.top_cost_items.map((i) => (
                <li
                  key={i.id}
                  className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border-subtle py-2 last:border-b-0"
                >
                  <span className="text-sm font-medium text-ink-primary">
                    {i.name}
                    {i.vendor ? (
                      <span className="ml-2 text-xs text-ink-tertiary">
                        ({i.vendor})
                      </span>
                    ) : null}
                  </span>
                  <div className="flex items-center gap-2">
                    {i.category ? (
                      <StatusPill tone="info">{i.category}</StatusPill>
                    ) : null}
                    <span className="text-sm font-semibold text-ink-primary">
                      {fmtUsd(i.annual_cost_usd)}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
