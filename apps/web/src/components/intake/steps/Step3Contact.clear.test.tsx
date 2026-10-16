import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Step3Contact } from "./Step3Contact";

/**
 * #1198 item 1, the web half (#736 6216024281: "title and phone are
 * clearable; display_name is not"). An emptied title or phone is SENT as
 * null, so the api's clear path is reached. It used to send
 * `value || undefined`, which `JSON.stringify` drops, so the save was a no-op
 * and the old value came back on reload.
 */

const DEFAULTS = {
  display_name: "Pat Example",
  title: "CISO",
  phone: "555-0100",
  timezone: "America/Chicago",
  email: "pat@example.test",
};

const NO_OVERRIDE = {
  primary_contact_name: null,
  primary_contact_email: null,
  primary_contact_title: null,
  primary_contact_phone: null,
};

function renderStep() {
  const onSave = vi.fn();
  render(
    <Step3Contact defaults={DEFAULTS} override={NO_OVERRIDE} onSave={onSave} />,
  );
  return onSave;
}

function input(id: string): HTMLInputElement {
  return document.getElementById(id) as HTMLInputElement;
}

describe("Step3Contact: an emptied title or phone is cleared (#1198)", () => {
  it.each(["title", "phone"])("sends %s as null when emptied", (field) => {
    const onSave = renderStep();
    expect(input(field).value).not.toBe("");
    fireEvent.blur(input(field), { target: { value: "" } });
    expect(onSave).toHaveBeenLastCalledWith({ [field]: null });
    // The wire form: the key survives JSON, as null.
    expect(JSON.stringify(onSave.mock.lastCall?.[0])).toBe(`{"${field}":null}`);
  });

  it("still sends a typed title as typed", () => {
    const onSave = renderStep();
    fireEvent.blur(input("title"), { target: { value: "CTO" } });
    expect(onSave).toHaveBeenLastCalledWith({ title: "CTO" });
  });

  it("does not send a clear for an emptied display_name", () => {
    const onSave = renderStep();
    fireEvent.blur(input("display_name"), { target: { value: "" } });
    expect(JSON.stringify(onSave.mock.lastCall?.[0])).toBe("{}");
  });
});
