import "@testing-library/jest-dom/vitest";

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/tech_debt/client";
import type { CapabilityList, SavingsPreview } from "@/lib/tech_debt/types";

import { SavingsWhatIf } from "./SavingsWhatIf";

vi.mock("@/lib/tech_debt/client", () => ({
  previewSavings: vi.fn(),
  bulkSetDisposition: vi.fn(),
  proxyMessage: (err: unknown, fallback: string) =>
    err instanceof Error ? err.message : fallback,
}));

const m = vi.mocked(client);

function list(): CapabilityList {
  return {
    id: "list-1",
    service_id: "svc-1",
    version: 1,
    status: "draft",
    items: [
      { id: "wiz", name: "Wiz", annual_cost_usd: 350000, disposition: null },
      {
        id: "splunk",
        name: "Splunk",
        annual_cost_usd: 480000,
        disposition: "cut",
      },
    ],
  } as unknown as CapabilityList;
}

function preview(over: Partial<SavingsPreview> = {}): SavingsPreview {
  return {
    capability_list_id: "list-1",
    estimated_annual_savings: 830000,
    savings_cost_known: true,
    keep_count: 0,
    consolidate_count: 0,
    cut_count: 2,
    undecided_count: 0,
    ...over,
  };
}

function choose(name: string, value: string): void {
  fireEvent.change(
    screen.getByRole("combobox", { name: `What-if for ${name}` }),
    {
      target: { value },
    },
  );
}

describe("SavingsWhatIf (#804)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    m.previewSavings.mockReset();
    m.bulkSetDisposition.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("asks the server nothing until a tool is ticked", () => {
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={vi.fn()}
      />,
    );
    expect(m.previewSavings).not.toHaveBeenCalled();
    expect(screen.getByTestId("what-if-current")).toHaveTextContent("$480,000");
  });

  it("shows the server's figure for the ticked tools, debounced", async () => {
    m.previewSavings.mockResolvedValue(preview());
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={vi.fn()}
      />,
    );
    choose("Wiz", "cut");
    choose("Wiz", "consolidate");
    choose("Wiz", "cut");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    // One request for the last choice, not one per change.
    expect(m.previewSavings).toHaveBeenCalledTimes(1);
    expect(m.previewSavings).toHaveBeenCalledWith("list-1", { wiz: "cut" });
    expect(screen.getByTestId("what-if-savings")).toHaveTextContent("$830,000");
  });

  it("says when the figure is a lower bound", async () => {
    m.previewSavings.mockResolvedValue(
      preview({ estimated_annual_savings: 480000, savings_cost_known: false }),
    );
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={vi.fn()}
      />,
    );
    choose("Wiz", "cut");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(screen.getByTestId("what-if-savings")).toHaveTextContent(
      "≥ $480,000",
    );
    expect(screen.getByTestId("what-if-savings-note")).toBeInTheDocument();
  });

  it("applies the what-if through the disposition route, one call per choice", async () => {
    m.previewSavings.mockResolvedValue(preview());
    const applied = { ...list(), version: 1 } as CapabilityList;
    m.bulkSetDisposition.mockResolvedValue(applied);
    const onApplied = vi.fn();
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={onApplied}
      />,
    );
    choose("Wiz", "consolidate");
    choose("Splunk", "keep");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    vi.useRealTimers();
    fireEvent.click(screen.getByRole("button", { name: "Apply to plan" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(applied));
    expect(m.bulkSetDisposition).toHaveBeenCalledWith(
      "list-1",
      ["wiz"],
      "consolidate",
    );
    expect(m.bulkSetDisposition).toHaveBeenCalledWith(
      "list-1",
      ["splunk"],
      "keep",
    );
    expect(m.bulkSetDisposition).toHaveBeenCalledTimes(2);
  });

  it("drops a choice set back to 'as planned' instead of sending it", async () => {
    m.previewSavings.mockResolvedValue(preview());
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={vi.fn()}
      />,
    );
    choose("Wiz", "cut");
    choose("Wiz", "");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(m.previewSavings).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Apply to plan" }),
    ).toBeDisabled();
  });

  it("shows the API's refusal rather than a figure", async () => {
    m.previewSavings.mockRejectedValue(
      new Error("Reload the list and try again."),
    );
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={vi.fn()}
      />,
    );
    choose("Wiz", "cut");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Reload the list and try again.",
    );
    expect(screen.queryByTestId("what-if-savings")).toBeNull();
  });

  it("shows no ATT&CK coverage figure", () => {
    render(
      <SavingsWhatIf
        list={list()}
        planSavings={480000}
        planKnown
        onApplied={vi.fn()}
      />,
    );
    expect(screen.queryByText(/coverage/i)).toBeNull();
    expect(screen.queryByText(/ATT&CK/)).toBeNull();
  });
});
