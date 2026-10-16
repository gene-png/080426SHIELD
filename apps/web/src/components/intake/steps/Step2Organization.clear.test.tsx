import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Step2Organization } from "./Step2Organization";
import type { IntakeStateResponse } from "@/lib/intake/types";

/**
 * #1093 item 1, the web half: a field the client empties is SENT as null, so
 * the api's clear path is reached. It used to send `value || undefined`, and
 * `JSON.stringify` drops an undefined key, so the save was a no-op and the old
 * value came back on reload.
 */

const SAVED = {
  legal_name: "Acme Corp",
  dba_name: "Acme",
  website: "https://acme.example/",
  size_band: "51-200",
  industry: "Manufacturing",
  address_line1: "1 Main St",
  address_line2: "Suite 2",
  city: "Springfield",
  state: "IL",
  postal_code: "62701",
  country: "US",
};

function renderStep(onSave = vi.fn()) {
  render(
    <Step2Organization
      state={{ client: SAVED } as unknown as IntakeStateResponse}
      onSave={onSave}
    />,
  );
  return onSave;
}

describe("Step2Organization: an emptied field is cleared (#1093)", () => {
  it.each(Object.keys(SAVED))("sends %s as null when emptied", (field) => {
    const onSave = renderStep();
    const input = document.getElementById(field) as HTMLInputElement;
    expect(input.value).not.toBe("");
    fireEvent.blur(input, { target: { value: "" } });
    expect(onSave).toHaveBeenLastCalledWith({ [field]: null });
    // The wire form: the key survives JSON, as null.
    expect(JSON.stringify(onSave.mock.lastCall?.[0])).toBe(`{"${field}":null}`);
  });

  it("still sends a typed value as typed", () => {
    const onSave = renderStep();
    fireEvent.blur(screen.getByLabelText("City"), {
      target: { value: "Shelbyville" },
    });
    expect(onSave).toHaveBeenLastCalledWith({ city: "Shelbyville" });
  });
});
