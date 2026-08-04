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
  /** When true (released list), inputs render read-only. */
  readOnly?: boolean;
}

type SaveStateById = Record<string, "idle" | "saving" | "saved" | "error">;

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
  readOnly = false,
}: EditableCapabilityTableProps): JSX.Element {
  const [saveState, setSaveState] = React.useState<SaveStateById>({});

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
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead className="sticky top-0 z-base bg-surface-sunken text-xs uppercase tracking-wider text-ink-secondary">
          <tr>
            <th
              className="border-b border-border-subtle px-3 py-2 text-left font-semibold"
              style={{ width: "8.5rem" }}
            >
              Confidence
            </th>
            <th
              className="border-b border-border-subtle px-3 py-2 text-left font-semibold"
              style={{ width: "9rem" }}
            >
              Disposition
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-left font-semibold">
              Name
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-left font-semibold">
              Vendor
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-left font-semibold">
              Category
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-left font-semibold">
              Function
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-right font-semibold">
              Annual cost (USD)
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-right font-semibold">
              Licenses
            </th>
            <th className="border-b border-border-subtle px-3 py-2 text-left font-semibold">
              Notes
            </th>
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
            items.map((item) => {
              const state = saveState[item.id] ?? "idle";
              return (
                <tr
                  key={item.id}
                  className={cn(
                    "border-b border-border-subtle last:border-b-0",
                    item.confidence_pct !== null &&
                      item.confidence_pct < 70 &&
                      "bg-status-warning-bg/30",
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
                        className={selectClasses}
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
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value;
                        if (v && v !== item.name) {
                          void save(item, { name: v });
                        }
                      }}
                      className={inputClasses}
                      aria-label="Name"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.vendor ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.vendor) {
                          void save(item, { vendor: v });
                        }
                      }}
                      className={inputClasses}
                      aria-label="Vendor"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.category ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.category) {
                          void save(item, { category: v });
                        }
                      }}
                      className={inputClasses}
                      aria-label="Category"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.function ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.function) {
                          void save(item, { function: v });
                        }
                      }}
                      className={inputClasses}
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
                      className={cn(inputClasses, "text-right")}
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
                      className={cn(inputClasses, "text-right")}
                      aria-label="License count"
                    />
                  </td>
                  <td className="border-b border-border-subtle px-3 py-2 align-top">
                    <input
                      type="text"
                      defaultValue={item.notes ?? ""}
                      readOnly={readOnly}
                      onBlur={(e) => {
                        const v = e.target.value || undefined;
                        if (v !== item.notes) {
                          void save(item, { notes: v });
                        }
                      }}
                      className={inputClasses}
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
