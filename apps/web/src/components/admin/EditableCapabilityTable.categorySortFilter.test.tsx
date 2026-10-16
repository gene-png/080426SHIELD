import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityItem } from "@/lib/tech_debt/types";

vi.mock("@/lib/tech_debt/client", () => ({
  patchCapabilityItem: vi.fn(),
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error && err.message ? err.message : fallback,
}));

import { EditableCapabilityTable } from "./EditableCapabilityTable";

/**
 * #1175: "Sort and filter dispositions by category." Strings approved on #736
 * (6206818759 item 7): "Filter by category", "Sort by category", "Showing {k}
 * of {n} rows", "Clear filter". Typed here, never imported from the component.
 */

function row(
  id: string,
  category: string | null,
  parent: string | null = null,
): CapabilityItem {
  return {
    id,
    capability_list_id: "list-1",
    name: id,
    vendor: null,
    category,
    function: null,
    annual_cost_usd: parent ? null : 100,
    license_count: null,
    notes: null,
    confidence_pct: 90,
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
    parent_item_id: parent,
  };
}

// List order: zeta (SIEM), alpha (EDR), suite (Productivity) with a part in
// EDR, none (null), beta (EDR).
const ITEMS = [
  row("zeta", "SIEM/SOAR"),
  row("alpha", "EDR/XDR"),
  row("suite", "Productivity/Content"),
  row("part", "EDR/XDR", "suite"),
  row("none", null),
  row("beta", "EDR/XDR"),
];

function names(): string[] {
  return screen
    .getAllByRole("textbox", { name: "Name" })
    .map((i) => (i as HTMLInputElement).value);
}

function filterTo(...values: string[]): void {
  const sel = screen.getByRole("listbox", {
    name: "Filter by category",
  }) as HTMLSelectElement;
  for (const o of Array.from(sel.options))
    o.selected = values.includes(o.value);
  fireEvent.change(sel);
}

describe("sort by category (#1175)", () => {
  it("cycles ascending, descending, then the list's own order, keeping a part under its bundle", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    // POSITIVE CONTROL: the list's own order, part under its bundle.
    expect(names()).toEqual(["zeta", "alpha", "suite", "part", "none", "beta"]);
    const sort = screen.getByRole("button", { name: "Sort by category" });
    fireEvent.click(sort);
    // EDR/XDR, Productivity/Content (with its part), SIEM/SOAR, Uncategorized.
    expect(names()).toEqual(["alpha", "beta", "suite", "part", "zeta", "none"]);
    expect(
      screen.getByRole("columnheader", { name: /category/i }),
    ).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(sort);
    expect(names()).toEqual(["none", "zeta", "suite", "part", "alpha", "beta"]);
    fireEvent.click(sort);
    expect(names()).toEqual(["zeta", "alpha", "suite", "part", "none", "beta"]);
  });
});

describe("filter by category (#1175)", () => {
  it("offers the categories present, Uncategorized included", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    const opts = Array.from(
      (
        screen.getByRole("listbox", {
          name: "Filter by category",
        }) as HTMLSelectElement
      ).options,
      (o) => o.value,
    );
    expect(opts).toEqual([
      "EDR/XDR",
      "Productivity/Content",
      "SIEM/SOAR",
      "Uncategorized",
    ]);
  });

  it("shows only the chosen categories, with the count, matching each row on its own category", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    expect(screen.queryByText(/^Showing \d+ of \d+ rows$/)).toBeNull();
    filterTo("EDR/XDR");
    // The part matches on ITS category, shown without its bundle.
    expect(names()).toEqual(["alpha", "part", "beta"]);
    expect(screen.getByText("Showing 3 of 6 rows")).toBeInTheDocument();
    filterTo("EDR/XDR", "Uncategorized");
    expect(names()).toEqual(["alpha", "part", "none", "beta"]);
    expect(screen.getByText("Showing 4 of 6 rows")).toBeInTheDocument();
  });

  it("Clear filter shows every row again", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    filterTo("SIEM/SOAR");
    expect(names()).toEqual(["zeta"]);
    fireEvent.click(screen.getByRole("button", { name: "Clear filter" }));
    expect(names()).toHaveLength(6);
    expect(screen.queryByText(/^Showing \d+ of \d+ rows$/)).toBeNull();
  });

  it("selects only the rows shown, so a bulk action cannot reach a hidden row", async () => {
    const onBulk = vi.fn().mockResolvedValue(undefined);
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={onBulk}
      />,
    );
    filterTo("EDR/XDR");
    fireEvent.click(screen.getByRole("checkbox", { name: "Select every row" }));
    fireEvent.change(
      screen.getByRole("combobox", { name: "Disposition for selected rows" }),
      {
        target: { value: "keep" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply to 3 rows" }));
    await waitFor(() => expect(onBulk).toHaveBeenCalledTimes(1));
    expect(onBulk).toHaveBeenCalledWith(["alpha", "part", "beta"], "keep");
  });
});
