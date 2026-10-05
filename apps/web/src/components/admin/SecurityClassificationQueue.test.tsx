import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CapabilityItem, CapabilityList } from "@/lib/tech_debt/types";

vi.mock("@/lib/tech_debt/client", () => ({
  confirmSecurityClassification: vi.fn(),
  overrideSecurityClassification: vi.fn(),
}));

import { confirmSecurityClassification } from "@/lib/tech_debt/client";

import { SecurityClassificationQueue } from "./SecurityClassificationQueue";

/**
 * #845: the sign-off queue gives a security tool the extraction marked "not in
 * use" its own group and wording, shows every row's note, and says what to do
 * next. Every string is the approved copy, written out (issue 845 comment
 * 5983735296; 736 comment 5986057990).
 */

function item(over: Partial<CapabilityItem>): CapabilityItem {
  return {
    id: over.name ?? "x",
    capability_list_id: "l",
    name: "x",
    vendor: null,
    category: null,
    function: null,
    annual_cost_usd: null,
    license_count: null,
    notes: null,
    confidence_pct: 60,
    security_related: false,
    security_functions: [],
    security_class_confirmed: false,
    source_artifact_id: null,
    disposition: null,
    disposition_rationale: null,
    consolidation_target_id: null,
    ...over,
  };
}

function list(items: CapabilityItem[], contradictions = 0): CapabilityList {
  return {
    id: "l",
    service_id: "s",
    version: 1,
    status: "draft",
    items,
    approved_at: null,
    approval_current: false,
    approved_by: null,
    not_in_use_contradictions: contradictions,
  };
}

const PLANNED = item({
  id: "p",
  name: "Falcon Identity",
  notes: "Security tool not in use: planned, not yet deployed.",
  signoff_kind: "not_in_use",
});
const PAYROLL = item({
  id: "w",
  name: "Workday HCM",
  signoff_kind: "not_security",
});

describe("SecurityClassificationQueue (#845)", () => {
  beforeEach(() => vi.mocked(confirmSecurityClassification).mockReset());

  it("gives not-in-use security tools their own group and wording", () => {
    render(
      <SecurityClassificationQueue
        list={list([PLANNED, PAYROLL])}
        onUpdated={() => {}}
        editable
      />,
    );
    const group = screen.getByTestId("security-signoff-not-in-use");
    expect(group).toHaveTextContent("Security tools not in use (1)");
    expect(group).toHaveTextContent(
      "The AI found these security tools described as planned, not yet deployed, inactive or no longer used. Until you confirm, they stay in the ATT&CK tool mapping, where they can be credited as if deployed.",
    );
    expect(group).toHaveTextContent(
      "If the tool is in use, mark it security-related: it stays in the ATT&CK assessment.",
    );
    expect(group).toHaveTextContent(
      "Note: Security tool not in use: planned, not yet deployed.",
    );
    expect(
      screen.getByRole("button", { name: "Not in use: remove from ATT&CK" }),
    ).toBeTruthy();

    const ordinary = screen.getByTestId("security-signoff-not-security");
    expect(ordinary).toHaveTextContent("Confirm security classification (1)");
    expect(ordinary).toHaveTextContent(
      "Marking it security-related keeps it in the ATT&CK assessment.",
    );
    expect(ordinary).not.toHaveTextContent("Workday HCMNote:");

    expect(screen.getByTestId("security-signoff-procedure").textContent).toBe(
      "Clear this queue before you approve the list. If the list is already approved, choose Approve again after confirming, then use Run AI on the ATT&CK service so its mapping stops crediting these tools.",
    );
  });

  it("confirms a not-in-use row through the same sign-off endpoint", async () => {
    vi.mocked(confirmSecurityClassification).mockResolvedValue(list([PAYROLL]));
    const onUpdated = vi.fn();
    render(
      <SecurityClassificationQueue
        list={list([PLANNED, PAYROLL])}
        onUpdated={onUpdated}
        editable
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Not in use: remove from ATT&CK" }),
    );
    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
    expect(confirmSecurityClassification).toHaveBeenCalledWith("p");
  });

  it("shows no not-in-use group when no row carries the prefix", () => {
    render(
      <SecurityClassificationQueue
        list={list([PAYROLL])}
        onUpdated={() => {}}
        editable
      />,
    );
    // The ordinary group rendered (the positive state) before the absence.
    expect(screen.getByTestId("security-signoff-not-security")).toBeTruthy();
    expect(screen.queryByTestId("security-signoff-not-in-use")).toBeNull();
  });

  it("says nothing at all when there is nothing to show", () => {
    const { container } = render(
      <SecurityClassificationQueue
        list={list([])}
        onUpdated={() => {}}
        editable
      />,
    );
    expect(container.textContent).toBe("");
  });
});
