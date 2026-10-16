import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CostEstimatePrompt } from "./CostEstimatePrompt";

// TD-5 (for #1060): E1 to E3, approved on #736 (6205600298, ruled 6206818759).
// The AI status reads as ready, so the guard passes the click straight on.
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: { ready: true },
    phase: "ready",
    settled: () => Promise.resolve({ ready: true }),
    refresh: () => undefined,
  }),
  hasAcknowledgedOffline: () => false,
  acknowledgeOffline: () => undefined,
}));

const E3 =
  'AI estimates are based on typical list prices and the license counts in your inventory, not on your contracts. Each one is labelled "AI estimate", and you can overwrite it by editing the cost.';

function mount(over: Partial<Parameters<typeof CostEstimatePrompt>[0]> = {}) {
  const props = {
    noCostCount: 4,
    editable: true,
    busy: false,
    onEnterCosts: vi.fn(),
    onEstimate: vi.fn(),
    ...over,
  };
  render(<CostEstimatePrompt {...props} />);
  return props;
}

describe("CostEstimatePrompt (TD-5)", () => {
  it("states the count, both buttons, and the disclosure before any click", () => {
    mount();
    expect(
      screen.getByText(
        "These 4 tools have no cost, or none was provided. Enter costs, or let AI estimate?",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Enter costs", exact: true }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Let AI estimate", exact: true }),
    ).toBeInTheDocument();
    expect(screen.getByText(E3)).toBeInTheDocument();
  });

  it("uses the singular for one tool", () => {
    mount({ noCostCount: 1 });
    expect(
      screen.getByText(
        "This tool has no cost, or none was provided. Enter a cost, or let AI estimate?",
      ),
    ).toBeInTheDocument();
  });

  it("Enter costs asks the workspace to filter", () => {
    const props = mount();
    fireEvent.click(screen.getByRole("button", { name: "Enter costs" }));
    expect(props.onEnterCosts).toHaveBeenCalledTimes(1);
    expect(props.onEstimate).not.toHaveBeenCalled();
  });

  it("Let AI estimate starts the run with the acknowledged status", () => {
    const props = mount();
    fireEvent.click(screen.getByRole("button", { name: "Let AI estimate" }));
    expect(props.onEstimate).toHaveBeenCalledWith("live");
  });

  it("is disabled while a run is in progress", () => {
    mount({ busy: true });
    expect(
      screen.getByRole("button", { name: "Let AI estimate" }),
    ).toBeDisabled();
  });

  it("is not shown at 0 or on a list that is no longer editable", () => {
    // POSITIVE CONTROL first: the same props with a count do render.
    const { unmount } = render(
      <CostEstimatePrompt
        noCostCount={2}
        editable
        busy={false}
        onEnterCosts={vi.fn()}
        onEstimate={vi.fn()}
      />,
    );
    expect(screen.getByTestId("cost-estimate-prompt")).toBeInTheDocument();
    unmount();
    mount({ noCostCount: 0 });
    expect(screen.queryByTestId("cost-estimate-prompt")).toBeNull();
  });

  it("is not shown on a released list", () => {
    mount({ editable: false });
    expect(screen.queryByTestId("cost-estimate-prompt")).toBeNull();
  });
});
