import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ZtStagePicker } from "./ZtStagePicker";

/**
 * Z3 (#736 6204461502 section 6, approved at 6205956728): the stage buttons
 * show the name alone; `S{n} {name}` is gone, on CISA and DoD alike.
 */

const CISA = [
  { stage: 1, label: "Traditional", description: "" },
  { stage: 2, label: "Initial", description: "" },
  { stage: 3, label: "Advanced", description: "" },
  { stage: 4, label: "Optimal", description: "" },
];
const DOD = [
  { stage: 1, label: "Below Target", description: "" },
  { stage: 2, label: "Target", description: "" },
  { stage: 3, label: "Advanced", description: "" },
];

describe("ZtStagePicker Z3: the stage name alone", () => {
  it.each([
    ["CISA", CISA, ["Traditional", "Initial", "Advanced", "Optimal"]],
    ["DoD", DOD, ["Below Target", "Target", "Advanced"]],
  ])("%s buttons read as their names", (_fw, stages, names) => {
    render(<ZtStagePicker value={2} onChange={() => {}} stages={stages} />);
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.textContent)).toEqual(names);
    expect(screen.getByRole("radio", { name: names[1] })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    for (const r of radios) expect(r.textContent).not.toMatch(/^S\d/);
  });
});
