"use client";
import * as React from "react";

import { cn, StatusPill } from "@shield/design-system";

import { patchCapabilityItem } from "@/lib/tech_debt/client";
import type {
  CapabilityDisposition,
  CapabilityItem,
  CapabilityItemPatch,
} from "@/lib/tech_debt/types";

import { inputClasses, selectClasses } from "../intake/Field";

import type { JSX } from "react";

export interface EditableCapabilityTableProps {
  items: CapabilityItem[];
  onItemUpdate: (next: CapabilityItem) => void;
  /**
   * Name the capabilities inside a bundled licence (UX finding 5). Omitted on
   * read-only lists.
   */
  onSplitBundle?: (item: CapabilityItem) => void;
  /** When true (released list), inputs render read-only. */
  readOnly?: boolean;
}

type SaveStateById = Record<string, "idle" | "saving" | "saved" | "error">;

// #643: an input or select with no width keeps its intrinsic ~20-character
// width, so seven of them overflowed the content column. Sized to the cell
// instead, and every column has an explicit width below.
//
// EVERY column is sized, because `table-fixed` splits whatever the sized ones
// leave among the rest: the first fix sized four columns in a 60rem minimum and
// left five text columns about 5.6rem each -- Name, the column step 2 exists to
// review, showed five characters (#685 round 1). Nine editable columns do not
// fit legibly in the ~62rem content column at 1280px, so the table keeps a
// minimum equal to their sum and scrolls sideways below it: a moderate scroll
// with a readable Name, over no scroll and an unreadable one. Name and Vendor
// get the room. The e2e spec `s44-techdebt-table-width` measures Name at 1280px
// and 1440px against a 24-character string in the input's own font.
const COLUMNS: ReadonlyArray<{
  label: string;
  rem: number;
  numeric?: boolean;
}> = [
  { label: "Confidence", rem: 7.5 },
  { label: "Disposition", rem: 8.5 },
  { label: "Name", rem: 16 },
  { label: "Vendor", rem: 12 },
  { label: "Category", rem: 9 },
  { label: "Function", rem: 9 },
  { label: "Annual cost (USD)", rem: 7.5, numeric: true },
  { label: "Licenses", rem: 5.5, numeric: true },
  { label: "Notes", rem: 12 },
];
/** The sum of the columns, so no column is ever given the leftover. */
const TABLE_MIN_REM = COLUMNS.reduce((sum, col) => sum + col.rem, 0);

const cellInputClasses = cn(inputClasses, "w-full min-w-0");
const cellSelectClasses = cn(selectClasses, "w-full min-w-0");

function fmtCurrency(value: number | null): string {
  if (value === null) return "";
  return value.toLocaleString();
}

function parseCurrency(raw: string): number | null {
  const cleaned = raw.replace(/[^0-9.\-]/g, "").trim();
  if (cleaned === "" || cleaned === "-") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

function parseInt32(raw: string): number | null {
  const cleaned = raw.replace(/[^0-9\-]/g, "").trim();
  if (cleaned === "" || cleaned === "-") return null;
  const n = parseInt(cleaned, 10);
  return Number.isFinite(n) ? n : null;
}

/** AI Prompt §6.2: AI output renders as a real editable table, NOT as raw JSON. */
export function EditableCapabilityTable({
  items,
  onItemUpdate,
  onSplitBundle,
  readOnly = false,
}: EditableCapabilityTableProps): JSX.Element {
  const [saveState, setSaveState] = React.useState<SaveStateById>({});

  // Each bundle is immediately followed by the components named inside it, so
  // the relationship is readable without a tree widget (UX finding 5).
  const ordered = React.useMemo(() => {
    const children = new Map<string, CapabilityItem[]>();
    for (const it of items) {
      if (!it.parent_item_id) continue;
      const list = children.get(it.parent_item_id) ?? [];
      list.push(it);
      children.set(it.parent_item_id, list);
    }
    return items
      .filter((it) => !it.parent_item_id)
      .flatMap((parent) => [parent, ...(children.get(parent.id) ?? [])]);
  }, [items]);

  async function save(
    item: CapabilityItem,
    patch: CapabilityItemPatch,
  ): Promise<void> {
    setSaveState((s) => ({ ...s, [item.id]: "saving" }));
    try {
      const next = await patchCapabilityItem(item.id, patch);
      onItemUpdate(next);
      setSaveState((s) => ({ ...s, [item.id]: "saved" }));
    } catch {
      setSaveState((s) => ({ ...s, [item.id]: "error" }));
    }
  }

  function confidenceTone(
    pct: number | null,
  ): "success" | "warning" | "neutral" | "info" {
    if (pct === null) return "success"; // human-curated
    if (pct >= 85) return "info";
    if (pct >= 70) return "warning";
    return "neutral";
  }

  function dispositionTone(
    d: CapabilityDisposition | null,
  ): "success" | "warning" | "danger" | "neutral" {
    if (d === "keep") return "success";
    if (d === "consolidate") return "warning";
    if (d === "cut") return "danger";
    return "neutral";
  }

  function confidenceLabel(pct: number | null): string {
    if (pct === null) return "Human-curated";
    return `AI ${pct}%`;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border-subtle">
      <table
        className="w-full table-fixed border-separate border-spacing-0 text-sm"
        style={{ minWidth: `${TABLE_MIN_REM}rem` }}
      >
        <thead className="sticky top-0 z-base bg-surface-sunken text-xs uppercase tracking-wider text-ink-secondary">
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.label}
                className={cn(
                  "border-b border-border-subtle px-3 py-2 font-semibold",
                  col.numeric ? "text-right" : "text-left",
                )}
                style={{ width: `${col.rem}rem` }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-surface-card">
          {items.length === 0 ? (
            <tr>
              <td
                colSpan={9}
                className="px-3 py-12 text-center text-sm text-ink-tertiary"
              >
                No items in this capability list. Run a new extraction.
              </td>
            </tr>
          ) : (
            ordered.map((item) => {
              const state = saveState[item.id] ?? "idle";
              const isComponent = Boolean(item.parent_item_id);
              return (
                <tr
                  key={item.id}
                  className={cn(
                    "border-b border-border-subtle last:border-b-0",
                    item.confidence_pct !== null &&
                      item.confidence_pct < 70 &&
                      "bg-status-warning-bg/30",
                    isComponent && "bg-surface-sunken/40",
                  )}
                >
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <div className="flex flex-col gap-1">
                      <StatusPill
                        tone={confidenceTone(item.confidence_pct)}
                        withDot
                      >
                        {confidenceLabel(item.confidence_pct)}
                      </StatusPill>
                      {state === "saving" ? (
                        <span className="text-xs text-ink-tertiary">
                          Saving…
                        </span>
                      ) : state === "saved" ? (
                        <span className="text-xs text-status-success-fg">
                          Saved
                        </span>
                      ) : state === "error" ? (
                        <span className="text-xs text-status-danger-fg">
                          Save failed
                        </span>
                      ) : null}
                      {isComponent ? (
                        <span className="text-xs text-ink-tertiary">
                          in bundle
                        </span>
                      ) : onSplitBundle ? (
                        <button
                          type="button"
                          onClick={() => onSplitBundle(item)}
                          className="text-left text-xs font-medium text-brand-600 underline hover:text-brand-700"
                        >
                          Split bundle…
                        </button>
                      ) : null}
                    </div>
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <div className="flex flex-col gap-1">
                      <select
                        defaultValue={item.disposition ?? ""}
                        disabled={readOnly}
                        onChange={(e) => {
                          const v = (e.target.value ||
                            null) as CapabilityDisposition | null;
                          if (v !== item.disposition) {
                            void save(item, { disposition: v });
                          }
                        }}
                        className={cellSelectClasses}
                        aria-label="Disposition"
                      >
                        <option value="">Undecided…</option>
                        <option value="keep">Keep</option>
                        <option value="consolidate">Consolidate</option>
                        <option value="cut">Cut</option>
                      </select>
                      {item.disposition ? (
                        <StatusPill tone={dispositionTone(item.disposition)}>
                          {item.disposition === "keep"
                            ? "Keep"
                            : item.disposition === "consolidate"
                              ? "Consolidate"
                              : "Cut"}
                        </StatusPill>
                      ) : null}
                    </div>
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.name}
                      title={item.name}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value;
                        if (v && v !== item.name) {
                          void save(item, { name: v });
                        }
                      }}
                      className={cellInputClasses}
                      aria-label="Name"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.vendor ?? ""}
                      title={item.vendor ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.vendor) {
                          void save(item, { vendor: v });
                        }
                      }}
                      className={cellInputClasses}
                      aria-label="Vendor"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.category ?? ""}
                      title={item.category ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.category) {
                          void save(item, { category: v });
                        }
                      }}
                      className={cellInputClasses}
                      aria-label="Category"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.function ?? ""}
                      title={item.function ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.function) {
                          void save(item, { function: v });
                        }
                      }}
                      className={cellInputClasses}
                      aria-label="Function"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top text-right">
                    <input
                      type="text"
                      defaultValue={fmtCurrency(item.annual_cost_usd)}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const next = parseCurrency(e.target.value);
                        if (next !== item.annual_cost_usd) {
                          void save(item, { annual_cost_usd: next });
                        }
                      }}
                      className={cn(cellInputClasses, "text-right")}
                      aria-label="Annual cost USD"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top text-right">
                    <input
                      type="text"
                      defaultValue={item.license_count ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const next = parseInt32(e.target.value);
                        if (next !== item.license_count) {
                          void save(item, { license_count: next });
                        }
                      }}
                      className={cn(cellInputClasses, "text-right")}
                      aria-label="License count"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.notes ?? ""}
                      title={item.notes ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.notes) {
                          void save(item, { notes: v });
                        }
                      }}
                      className={cellInputClasses}
                      aria-label="Notes"
                    />
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
