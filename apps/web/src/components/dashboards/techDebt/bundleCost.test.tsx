import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type {
  TechDebtDashboardData,
  TechDebtItem,
} from "@/lib/dashboards/techDebt";

import { TechDebtDashboard } from "./TechDebtDashboard";

// for #929: a split bundle's part has no cost of its own, so its cost cell
// names the bundle that carries it ("Included in {bundle}", approved copy on
// #736) instead of "—", which reads as an unknown cost. The API sends `bundle`
// as the bundle's name, "" when that name is blank, and null for a row that is
// not a part. Rendered through the real dashboard, in both places a row's cost
// shows: the inventory table and the redundancy card.

function row(
  name: string,
  cost: number | null,
  bundle: string | null,
): TechDebtItem {
  return {
    name,
    vendor: null,
    category: "EDR",
    function: null,
    annual_cost_usd: cost,
    license_count: null,
    disposition: "keep",
    notes: null,
    bundle,
  };
}

const PART = row("Microsoft Defender for Endpoint", null, "Microsoft 365 E5");
const BLANK_PART = row("Defender for Cloud Apps", null, "");
// A cost stored on a part before #927 refused one. Spend excludes it, so the
// cell must not show it.
const LEGACY_PART = row("Microsoft Entra ID P2", 20000, "Microsoft 365 E5");
const UNCOSTED_TOOL = row("Homegrown EDR", null, null);
const TOOL = row("CrowdStrike Falcon", 120000, null);
const ROWS = [TOOL, PART, BLANK_PART, LEGACY_PART, UNCOSTED_TOOL];

function data(): TechDebtDashboardData {
  return {
    service_id: "11111111-1111-4111-8111-111111111111",
    service_title: "Tech Debt",
    released_at: "2026-10-08T00:00:00Z",
    deliverable_version: 1,
    ai_source: {
      state: "live",
      sentence: "AI suggestions in this assessment came from a live AI model.",
      live_runs: 1,
      fixture_runs: 0,
    },
    total_applications: 2,
    bundle_part_count: 3,
    annual_spend_usd: 120000,
    identified_savings_usd: 0,
    savings_cost_known: true,
    spend_completeness: "partial",
    source_rows_total: 2,
    included_count: 2,
    excluded_count: 0,
    excluded_count_exact: true,
    redundant_category_count: 1,
    spend_by_category: [],
    sprawl_by_category: [],
    redundancies: [{ category: "EDR", count: 3, savings_usd: 0, items: ROWS }],
    items: ROWS,
  } as unknown as TechDebtDashboardData;
}

/** The "Annual cost" cell of the inventory row for `name`, found by the
 *  column's header rather than by position. */
function costCell(name: string): HTMLElement {
  const table = screen.getByRole("table");
  const headers = within(table).getAllByRole("columnheader");
  const col = headers.findIndex((h) => h.textContent === "Annual cost");
  expect(col).toBeGreaterThanOrEqual(0);
  const tr = within(table).getByText(name).closest("tr");
  if (!tr) throw new Error(`no table row for ${name}`);
  const td = tr.querySelectorAll("td")[col];
  if (!td) throw new Error(`no cost cell for ${name}`);
  return td as HTMLElement;
}

function redundancyRow(name: string): HTMLElement {
  const table = screen.getByRole("table");
  const hits = screen.getAllByText(name).filter((el) => !table.contains(el));
  expect(hits).toHaveLength(1);
  const div = hits[0].parentElement;
  if (!div) throw new Error(`no redundancy row for ${name}`);
  return div;
}

describe("a bundle part's cost names its bundle (#929)", () => {
  it("inventory: a part reads Included in its bundle's name", () => {
    render(<TechDebtDashboard data={data()} />);
    expect(costCell(PART.name)).toHaveTextContent(
      /^Included in Microsoft 365 E5$/,
    );
  });

  it("inventory: a part whose bundle has a blank name reads Included in its bundle", () => {
    render(<TechDebtDashboard data={data()} />);
    expect(costCell(BLANK_PART.name)).toHaveTextContent(
      /^Included in its bundle$/,
    );
  });

  it("inventory: a part holding a pre-#927 cost names its bundle, not the cost", () => {
    render(<TechDebtDashboard data={data()} />);
    expect(costCell(LEGACY_PART.name)).toHaveTextContent(
      /^Included in Microsoft 365 E5$/,
    );
  });

  it("inventory: a tool that is not a part keeps its cost, or — when it has none", () => {
    render(<TechDebtDashboard data={data()} />);
    expect(costCell(TOOL.name)).toHaveTextContent(/^\$120K$/);
    expect(costCell(UNCOSTED_TOOL.name)).toHaveTextContent(/^—$/);
  });

  it("redundancy card: parts name their bundle, tools keep their cost", () => {
    render(<TechDebtDashboard data={data()} />);
    expect(
      within(redundancyRow(PART.name)).getByText(
        "Included in Microsoft 365 E5",
      ),
    ).toBeInTheDocument();
    expect(
      within(redundancyRow(BLANK_PART.name)).getByText(
        "Included in its bundle",
      ),
    ).toBeInTheDocument();
    const legacy = redundancyRow(LEGACY_PART.name);
    expect(
      within(legacy).getByText("Included in Microsoft 365 E5"),
    ).toBeInTheDocument();
    expect(within(legacy).queryByText("$20K")).toBeNull();
    expect(
      within(redundancyRow(TOOL.name)).getByText("$120K"),
    ).toBeInTheDocument();
    expect(
      within(redundancyRow(UNCOSTED_TOOL.name)).getByText("—"),
    ).toBeInTheDocument();
  });
});
