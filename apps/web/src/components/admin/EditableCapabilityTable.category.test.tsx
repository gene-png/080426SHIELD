import "@testing-library/jest-dom/vitest";

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CapabilityItem } from "@/lib/tech_debt/types";

vi.mock("@/lib/tech_debt/client", () => ({
  patchCapabilityItem: vi.fn(),
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error && err.message ? err.message : fallback,
}));

import { patchCapabilityItem } from "@/lib/tech_debt/client";

import { EditableCapabilityTable } from "./EditableCapabilityTable";

/**
 * #1176: the category cell is a dropdown of the API's closed list plus
 * "Uncategorized" (null). Strings approved on #736 (6206818759 item 7). The
 * options come from the `categories` prop (the API), never from a copy here.
 */

const CATEGORIES = {
  categories: ["EDR/XDR", "SIEM/SOAR"],
  uncategorized_label: "Uncategorized",
};

function item(category: string | null): CapabilityItem {
  return {
    id: "item-1",
    capability_list_id: "list-1",
    name: "Tool",
    vendor: "Vendor",
    category,
    function: "Function",
    annual_cost_usd: 1000,
    license_count: 10,
    notes: "n",
    confidence_pct: 90,
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
  };
}

function cell(): HTMLSelectElement {
  return screen.getByRole("combobox", {
    name: "Category",
  }) as HTMLSelectElement;
}

function optionLabels(): string[] {
  return within(cell())
    .getAllByRole("option")
    .map((o) => o.textContent ?? "");
}

beforeEach(() => {
  vi.mocked(patchCapabilityItem).mockReset();
  vi.mocked(patchCapabilityItem).mockImplementation(async (_id, patch) => ({
    ...item(null),
    ...patch,
  }));
});

describe("the category dropdown (#1176)", () => {
  it("offers Uncategorized and exactly the API's list", () => {
    render(
      <EditableCapabilityTable
        items={[item("SIEM/SOAR")]}
        onItemUpdate={() => {}}
        categories={CATEGORIES}
      />,
    );
    expect(optionLabels()).toEqual(["Uncategorized", "EDR/XDR", "SIEM/SOAR"]);
    expect(cell().value).toBe("SIEM/SOAR");
    // Titled with its value, as the free-text cells are, so a long one reads.
    expect(cell()).toHaveAttribute("title", "SIEM/SOAR");
  });

  it("shows a stored value outside the list, selected, and does not remap it", () => {
    render(
      <EditableCapabilityTable
        items={[item("EDR")]}
        onItemUpdate={() => {}}
        categories={CATEGORIES}
      />,
    );
    expect(optionLabels()).toEqual([
      "Uncategorized",
      "EDR (not on the list)",
      "EDR/XDR",
      "SIEM/SOAR",
    ]);
    expect(cell().value).toBe("EDR");
    expect(patchCapabilityItem).not.toHaveBeenCalled();
  });

  it("saves a chosen category", async () => {
    render(
      <EditableCapabilityTable
        items={[item("EDR")]}
        onItemUpdate={() => {}}
        categories={CATEGORIES}
      />,
    );
    fireEvent.change(cell(), { target: { value: "EDR/XDR" } });
    await waitFor(() =>
      expect(patchCapabilityItem).toHaveBeenCalledWith("item-1", {
        category: "EDR/XDR",
      }),
    );
  });

  it("saves Uncategorized as null", async () => {
    render(
      <EditableCapabilityTable
        items={[item("SIEM/SOAR")]}
        onItemUpdate={() => {}}
        categories={CATEGORIES}
      />,
    );
    fireEvent.change(cell(), { target: { value: "" } });
    await waitFor(() =>
      expect(patchCapabilityItem).toHaveBeenCalledWith("item-1", {
        category: null,
      }),
    );
  });

  it("is disabled and shows only the stored value until the list is loaded", () => {
    render(
      <EditableCapabilityTable items={[item("EDR")]} onItemUpdate={() => {}} />,
    );
    expect(cell()).toBeDisabled();
    expect(optionLabels()).toEqual(["EDR"]);
  });

  it("is disabled on a released list", () => {
    render(
      <EditableCapabilityTable
        items={[item("SIEM/SOAR")]}
        onItemUpdate={() => {}}
        categories={CATEGORIES}
        readOnly
      />,
    );
    // POSITIVE CONTROL: the options rendered, so "disabled" is about readOnly.
    expect(optionLabels()).toHaveLength(3);
    expect(cell()).toBeDisabled();
  });
});
