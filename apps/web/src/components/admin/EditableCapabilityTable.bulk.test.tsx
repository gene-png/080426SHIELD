import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityItem } from "@/lib/tech_debt/types";

import { EditableCapabilityTable } from "./EditableCapabilityTable";

vi.mock("@/lib/tech_debt/client", () => ({
  patchCapabilityItem: vi.fn(),
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
}));

// #641: step 2 classified one row at a time. These drive the real table: tick
// rows, choose a disposition, apply once.
function item(id: string, name: string): CapabilityItem {
  return {
    id,
    capability_list_id: "list-1",
    name,
    vendor: null,
    category: null,
    function: null,
    annual_cost_usd: 1000,
    license_count: null,
    notes: null,
    confidence_pct: 90,
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
  };
}

const ITEMS = [item("a", "Alpha"), item("b", "Bravo"), item("c", "Charlie")];

function rowBox(name: string): HTMLElement {
  return screen.getByRole("checkbox", { name: `Select ${name}` });
}

function applyButton(): HTMLElement {
  return screen.getByRole("button", { name: /^Apply to/ });
}

function chooseBulk(value: string): void {
  fireEvent.change(
    screen.getByRole("combobox", { name: "Disposition for selected rows" }),
    { target: { value } },
  );
}

describe("EditableCapabilityTable bulk disposition (#641)", () => {
  it("offers no selection without a bulk handler, so other callers are unchanged", () => {
    render(<EditableCapabilityTable items={ITEMS} onItemUpdate={() => {}} />);
    expect(screen.getAllByRole("combobox")).toHaveLength(3);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("offers no selection on a read-only list, even with a handler", () => {
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
        readOnly
      />,
    );
    expect(screen.getAllByRole("combobox")).toHaveLength(3);
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("applies one disposition to exactly the ticked rows", async () => {
    const onBulk = vi.fn().mockResolvedValue(undefined);
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={onBulk}
      />,
    );
    fireEvent.click(rowBox("Alpha"));
    fireEvent.click(rowBox("Charlie"));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    chooseBulk("cut");
    await act(async () => {
      fireEvent.click(applyButton());
    });

    expect(onBulk).toHaveBeenCalledTimes(1);
    expect(onBulk).toHaveBeenCalledWith(["a", "c"], "cut");
    expect(screen.getByRole("status")).toHaveTextContent("Set 2 rows to Cut.");
    // The selection is spent once it has been applied.
    expect(rowBox("Alpha")).not.toBeChecked();
    expect(rowBox("Charlie")).not.toBeChecked();
  });

  it("sends null, not the string, when the rows go back to undecided", async () => {
    const onBulk = vi.fn().mockResolvedValue(undefined);
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={onBulk}
      />,
    );
    fireEvent.click(rowBox("Bravo"));
    chooseBulk("undecided");
    await act(async () => {
      fireEvent.click(applyButton());
    });
    expect(onBulk).toHaveBeenCalledWith(["b"], null);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Set 1 row to Undecided.",
    );
  });

  it("selects every row from the header checkbox, and clears them from it", () => {
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
      />,
    );
    const all = screen.getByRole("checkbox", { name: "Select every row" });
    fireEvent.click(all);
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    for (const n of ["Alpha", "Bravo", "Charlie"]) {
      expect(rowBox(n)).toBeChecked();
    }
    fireEvent.click(all);
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });

  it("will not apply until rows AND a disposition are chosen", () => {
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
      />,
    );
    expect(applyButton()).toBeDisabled();
    fireEvent.click(rowBox("Alpha"));
    // A row but no choice: an accidental click must not decide anything.
    expect(applyButton()).toBeDisabled();
    chooseBulk("keep");
    expect(applyButton()).toBeEnabled();
  });

  it("shows the server's refusal and keeps the selection for a retry", async () => {
    const onBulk = vi
      .fn()
      .mockRejectedValue(new Error("1 of the 2 selected rows are not here."));
    render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={onBulk}
      />,
    );
    fireEvent.click(rowBox("Alpha"));
    fireEvent.click(rowBox("Bravo"));
    chooseBulk("keep");
    await act(async () => {
      fireEvent.click(applyButton());
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "1 of the 2 selected rows are not here.",
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(rowBox("Alpha")).toBeChecked();
    expect(rowBox("Bravo")).toBeChecked();
  });

  it("shows each row's new disposition once the list comes back", () => {
    const { rerender } = render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
      />,
    );
    // The per-row select is uncontrolled; a bulk write arrives as new props,
    // and a select that kept its first value would show a stale decision.
    rerender(
      <EditableCapabilityTable
        items={ITEMS.map((i) => ({ ...i, disposition: "cut" as const }))}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
      />,
    );
    const rowSelects = screen.getAllByRole("combobox", { name: "Disposition" });
    expect(rowSelects).toHaveLength(3);
    for (const s of rowSelects) expect(s).toHaveValue("cut");
  });

  it("drops a selected row that leaves the list", () => {
    const { rerender } = render(
      <EditableCapabilityTable
        items={ITEMS}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
      />,
    );
    fireEvent.click(rowBox("Alpha"));
    fireEvent.click(rowBox("Bravo"));
    rerender(
      <EditableCapabilityTable
        items={ITEMS.slice(1)}
        onItemUpdate={() => {}}
        onBulkDisposition={vi.fn()}
      />,
    );
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });
});
