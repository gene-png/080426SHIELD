import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Step2Organization } from "./Step2Organization";
import type { IntakeStateResponse } from "@/lib/intake/types";

/**
 * #1200, option (a) on #736 (6216024281): no prefill. An empty stored country
 * renders as empty, so tabbing through the field can never save a default
 * over a value the client cleared (#1093 made the clear reachable).
 */

function renderStep(client: Record<string, unknown> | null) {
  const onSave = vi.fn();
  render(
    <Step2Organization
      state={{ client } as unknown as IntakeStateResponse}
      onSave={onSave}
    />,
  );
  return {
    onSave,
    country: document.getElementById("country") as HTMLInputElement,
  };
}

describe("Step2Organization: an empty country is shown empty (#1200)", () => {
  it.each([
    ["a cleared country", { legal_name: "Acme Corp", country: null }],
    ["a client with no country key", { legal_name: "Acme Corp" }],
    ["no client yet", null],
  ])("renders %s as an empty field", (_label, client) => {
    const { country } = renderStep(client);
    expect(country.value).toBe("");
  });

  it("a blur over a cleared country saves nothing but the clear", () => {
    const { onSave, country } = renderStep({
      legal_name: "Acme Corp",
      country: null,
    });
    fireEvent.blur(country);
    expect(onSave).toHaveBeenLastCalledWith({ country: null });
    expect(JSON.stringify(onSave.mock.calls)).not.toContain("United States");
  });

  it("still shows a stored country as stored", () => {
    const { country } = renderStep({
      legal_name: "Acme Corp",
      country: "Canada",
    });
    expect(country.value).toBe("Canada");
  });
});
