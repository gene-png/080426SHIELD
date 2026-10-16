import "@testing-library/jest-dom/vitest";

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CapabilityItem, CapabilityList } from "@/lib/tech_debt/types";

vi.mock("@/lib/tech_debt/client", () => ({
  bulkConfirmSecurityClassification: vi.fn(),
  confirmSecurityClassification: vi.fn(),
  overrideSecurityClassification: vi.fn(),
}));

import { bulkConfirmSecurityClassification } from "@/lib/tech_debt/client";

import { SecurityClassificationQueue } from "./SecurityClassificationQueue";

/**
 * #1174: "select all, then untick the exceptions". Strings approved on #736
 * (6206818759 item 7), typed here, never imported from the component.
 */

function item(id: string, notes: string | null = null): CapabilityItem {
  return {
    id,
    capability_list_id: "l",
    name: id,
    vendor: null,
    category: null,
    function: null,
    annual_cost_usd: null,
    license_count: null,
    notes,
    confidence_pct: 60,
    security_related: false,
    security_functions: [],
    security_class_confirmed: false,
    signoff_kind: notes ? "not_in_use" : "not_security",
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
  } as CapabilityItem;
}

function list(items: CapabilityItem[]): CapabilityList {
  return {
    id: "l",
    service_id: "s",
    version: 1,
    status: "draft",
    items,
    approved_at: null,
    approval_current: false,
    approved_by: null,
    not_in_use_contradictions: 0,
  } as unknown as CapabilityList;
}

const NOT_SECURITY = ["hr", "mail", "wiki"].map((id) => item(id));
const NOT_IN_USE = [item("old", "Security tool not in use: retired.")];

function card(testId: string): HTMLElement {
  return screen.getByTestId(testId);
}

beforeEach(() => {
  vi.mocked(bulkConfirmSecurityClassification).mockReset();
  vi.mocked(bulkConfirmSecurityClassification).mockResolvedValue(list([]));
});

describe("SecurityClassificationQueue bulk confirm (#1174)", () => {
  it("select all, then untick one, confirms exactly the rest", async () => {
    const onUpdated = vi.fn();
    render(
      <SecurityClassificationQueue
        list={list([...NOT_SECURITY, ...NOT_IN_USE])}
        onUpdated={onUpdated}
        editable
      />,
    );
    const c = within(card("security-signoff-not-security"));
    fireEvent.click(c.getByRole("checkbox", { name: "Select all (3)" }));
    expect(
      c.getByRole("button", { name: "Not security: confirm 3" }),
    ).toBeEnabled();
    fireEvent.click(c.getByRole("checkbox", { name: "Select mail" }));
    fireEvent.click(c.getByRole("button", { name: "Not security: confirm 2" }));
    await waitFor(() =>
      expect(bulkConfirmSecurityClassification).toHaveBeenCalledWith("l", [
        "hr",
        "wiki",
      ]),
    );
    await waitFor(() => expect(onUpdated).toHaveBeenCalledTimes(1));
  });

  it("uses the not-in-use wording on that card, singular for one", () => {
    render(
      <SecurityClassificationQueue
        list={list([...NOT_SECURITY, ...NOT_IN_USE])}
        onUpdated={vi.fn()}
        editable
      />,
    );
    const c = within(card("security-signoff-not-in-use"));
    fireEvent.click(c.getByRole("checkbox", { name: "Select all (1)" }));
    expect(
      c.getByRole("button", { name: "Not in use: remove 1 from ATT&CK" }),
    ).toBeEnabled();
  });

  it("is disabled with nothing ticked, and the cards' selections are separate", () => {
    render(
      <SecurityClassificationQueue
        list={list([...NOT_SECURITY, ...NOT_IN_USE])}
        onUpdated={vi.fn()}
        editable
      />,
    );
    const sec = within(card("security-signoff-not-security"));
    const old = within(card("security-signoff-not-in-use"));
    expect(
      sec.getByRole("button", { name: "Not security: confirm 0" }),
    ).toBeDisabled();
    fireEvent.click(old.getByRole("checkbox", { name: "Select all (1)" }));
    // Ticking the other card does not tick this one.
    expect(
      sec.getByRole("button", { name: "Not security: confirm 0" }),
    ).toBeDisabled();
  });

  it("shows the API's refusal and keeps the rows", async () => {
    vi.mocked(bulkConfirmSecurityClassification).mockRejectedValue(
      new Error("1 of the 3 selected rows do not need sign-off."),
    );
    const onUpdated = vi.fn();
    render(
      <SecurityClassificationQueue
        list={list(NOT_SECURITY)}
        onUpdated={onUpdated}
        editable
      />,
    );
    const c = within(card("security-signoff-not-security"));
    fireEvent.click(c.getByRole("checkbox", { name: "Select all (3)" }));
    fireEvent.click(c.getByRole("button", { name: "Not security: confirm 3" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "1 of the 3 selected rows do not need sign-off.",
    );
    expect(onUpdated).not.toHaveBeenCalled();
    // The list prop is the parent's and never changes here, so "the rows are
    // still listed" could not fail. What the component owns is the
    // selection: it is kept, and the bulk confirm can be sent again.
    await waitFor(() =>
      expect(
        c.getByRole("button", { name: "Not security: confirm 3" }),
      ).toBeEnabled(),
    );
    expect(c.getByRole("checkbox", { name: "Select hr" })).toBeChecked();
  });

  it("disables every row's own controls while a bulk confirm is in flight", async () => {
    let finish: (l: CapabilityList) => void = () => undefined;
    vi.mocked(bulkConfirmSecurityClassification).mockReturnValue(
      new Promise<CapabilityList>((resolve) => {
        finish = resolve;
      }),
    );
    render(
      <SecurityClassificationQueue
        list={list(NOT_SECURITY)}
        onUpdated={vi.fn()}
        editable
      />,
    );
    const c = within(card("security-signoff-not-security"));
    // POSITIVE CONTROL: a row's own confirm is enabled before the bulk click.
    const rowConfirms = c.getAllByRole("button", {
      name: "Not security — confirm",
    });
    expect(rowConfirms[0]).toBeEnabled();
    fireEvent.click(c.getByRole("checkbox", { name: "Select all (3)" }));
    fireEvent.click(c.getByRole("button", { name: "Not security: confirm 3" }));
    await waitFor(() => expect(rowConfirms[0]).toBeDisabled());
    for (const b of rowConfirms) expect(b).toBeDisabled();
    // ...and they come back once the request has finished.
    finish(list(NOT_SECURITY));
    await waitFor(() => expect(rowConfirms[0]).toBeEnabled());
    for (const b of rowConfirms) expect(b).toBeEnabled();
  });

  it("offers no selection on a locked list", () => {
    render(
      <SecurityClassificationQueue
        list={list(NOT_SECURITY)}
        onUpdated={vi.fn()}
        editable={false}
      />,
    );
    // POSITIVE CONTROL: the card rendered its rows.
    expect(screen.getByText("hr")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Select all/ })).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Not security: confirm/ }),
    ).toBeNull();
  });
});
