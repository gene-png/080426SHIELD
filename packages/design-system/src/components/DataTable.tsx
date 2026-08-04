import * as React from "react";

import { cn } from "../utils/cn";

import type { JSX } from "react";

export interface DataTableColumn<Row> {
  /** Column key - must be unique within the table. */
  key: string;
  /** Header text. */
  header: React.ReactNode;
  /** Cell renderer. */
  cell: (row: Row, rowIndex: number) => React.ReactNode;
  /** Tailwind alignment override for the column. */
  align?: "left" | "right" | "center";
  /** When true, the column shows a sort affordance and emits onSort events. */
  sortable?: boolean;
  /** When set, fixes the column to a width so the layout doesn't reflow per page. */
  width?: string;
}

export interface DataTableProps<Row> {
  caption?: React.ReactNode;
  columns: DataTableColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row, rowIndex: number) => string;
  /** Sticky header. Default true for operational density. */
  stickyHeader?: boolean;
  /** Currently-sorted column key. */
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  onSort?: (key: string, direction: "asc" | "desc") => void;
  /** Optional row click handler (admin workspaces - drill-down). */
  onRowClick?: (row: Row, rowIndex: number) => void;
  /** Rendered when `rows` is empty. */
  emptyState?: React.ReactNode;
  className?: string;
}

const ALIGN: Record<NonNullable<DataTableColumn<unknown>["align"]>, string> = {
  left: "text-left",
  right: "text-right",
  center: "text-center",
};

export function DataTable<Row>(props: DataTableProps<Row>): JSX.Element {
  const {
    caption,
    columns,
    rows,
    rowKey,
    stickyHeader = true,
    sortKey,
    sortDirection,
    onSort,
    onRowClick,
    emptyState,
    className,
  } = props;

  function handleHeaderClick(col: DataTableColumn<Row>): void {
    if (!col.sortable || !onSort) return;
    const nextDir: "asc" | "desc" =
      sortKey === col.key && sortDirection === "asc" ? "desc" : "asc";
    onSort(col.key, nextDir);
  }

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-lg border border-border-subtle",
        className,
      )}
    >
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        {caption ? (
          <caption className="bg-surface-sunken px-4 py-2 text-left text-xs text-ink-secondary">
            {caption}
          </caption>
        ) : null}
        <thead
          className={cn(
            "bg-surface-sunken text-xs uppercase tracking-wider text-ink-secondary",
            stickyHeader && "sticky top-0 z-base",
          )}
        >
          <tr>
            {columns.map((col) => {
              const sorted = sortKey === col.key;
              return (
                <th
                  key={col.key}
                  scope="col"
                  className={cn(
                    "border-b border-border-subtle px-4 py-2 font-semibold",
                    ALIGN[col.align ?? "left"],
                    col.sortable &&
                      "cursor-pointer select-none hover:text-ink-primary",
                  )}
                  style={col.width ? { width: col.width } : undefined}
                  aria-sort={
                    sorted
                      ? sortDirection === "asc"
                        ? "ascending"
                        : "descending"
                      : col.sortable
                        ? "none"
                        : undefined
                  }
                  onClick={
                    col.sortable ? () => handleHeaderClick(col) : undefined
                  }
                  onKeyDown={
                    col.sortable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            handleHeaderClick(col);
                          }
                        }
                      : undefined
                  }
                  tabIndex={col.sortable ? 0 : -1}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.header}
                    {col.sortable ? (
                      <span aria-hidden className="text-ink-tertiary">
                        {sorted ? (sortDirection === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    ) : null}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="bg-surface-card">
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-12 text-center text-ink-tertiary"
              >
                {emptyState ?? "No records."}
              </td>
            </tr>
          ) : (
            rows.map((row, rowIndex) => (
              <tr
                key={rowKey(row, rowIndex)}
                className={cn(
                  "border-b border-border-subtle last:border-b-0",
                  onRowClick && "cursor-pointer hover:bg-surface-sunken",
                )}
                onClick={
                  onRowClick ? () => onRowClick(row, rowIndex) : undefined
                }
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "border-b border-border-subtle px-4 py-2 text-ink-primary last:border-b-0",
                      ALIGN[col.align ?? "left"],
                    )}
                  >
                    {col.cell(row, rowIndex)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
