import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ZtStagePicker } from "./ZtStagePicker";

/**
 * #922: a stage above the capability's own maximum is shown but unavailable
 * (aria-disabled, no change on click or Space), so nobody picks a stage the
 * API refuses. Kept in place, so keyboard focus and the button count do not
 * change. A stage already stored above the maximum can still be cleared.
 */

const DOD = [
  { stage: 1, label: "Below Target", description: "" },
  { stage: 2, label: "Target", description: "" },
  { stage: 3, label: "Advanced", description: "" },
];

describe("ZtStagePicker #922: stages above the capability's maximum", () => {
  it("marks the unreachable stage unavailable and ignores a click on it", () => {
    const onChange = vi.fn();
    render(
      <ZtStagePicker
        value={null}
        onChange={onChange}
        stages={DOD}
        maxStage={2}
      />,
    );
    // The positive state first: the reachable stages work.
    fireEvent.click(screen.getByRole("radio", { name: "Target" }));
    expect(onChange).toHaveBeenCalledWith(2);
    onChange.mockClear();

    const advanced = screen.getByRole("radio", { name: "Advanced" });
    expect(advanced).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(advanced);
    // jsdom fires no click from a key, so this guards only against a future
    // onKeyDown that selects; a real Space or Enter is a click, caught above.
    fireEvent.keyDown(advanced, { key: " " });
    expect(onChange).not.toHaveBeenCalled();
    // Still in place: three buttons, in order.
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("radio", { name: "Target" })).not.toHaveAttribute(
      "aria-disabled",
    );
  });

  it("lets a stage already stored above the maximum be cleared", () => {
    const onChange = vi.fn();
    render(
      <ZtStagePicker value={3} onChange={onChange} stages={DOD} maxStage={2} />,
    );
    const advanced = screen.getByRole("radio", { name: "Advanced" });
    expect(advanced).toHaveAttribute("aria-checked", "true");
    fireEvent.click(advanced);
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("offers every stage when no maximum is given", () => {
    render(<ZtStagePicker value={null} onChange={() => {}} stages={DOD} />);
    for (const r of screen.getAllByRole("radio")) {
      expect(r).not.toHaveAttribute("aria-disabled");
    }
  });
});
