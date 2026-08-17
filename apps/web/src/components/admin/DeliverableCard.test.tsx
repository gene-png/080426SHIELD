import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DeliverableCard } from "./DeliverableCard";
import type { Deliverable } from "@/lib/tech_debt/types";

vi.mock("@/lib/tech_debt/client", () => ({
  finalizeDeliverable: vi.fn(),
  releaseDeliverable: vi.fn(),
  TechDebtProxyError: class extends Error {},
}));

/**
 * The Tech Debt finalize control (W4, D-046).
 *
 * This component had no test, and that is exactly why it shipped the defect the
 * API half of W4 was written to avoid: `canFinalize` required the capability
 * list to be exactly `"approved"`, while its three siblings
 * (Csf/Zt/AttackDeliverableCard) accept `"approved"` or `"released"`. Once
 * release flips the list to RELEASED, the `=== "approved"` form greys out the
 * only finalize control in the product — permanently, and with no reason shown,
 * because the explanatory hint only renders when no deliverable exists.
 *
 * The API-side test asserts 201 on the same call, so it passes over this: it
 * proves the route, not the product.
 */
function deliverable(overrides: Partial<Deliverable> = {}): Deliverable {
  return {
    id: "d1",
    service_id: "s1",
    title: "Atlas — Tech Debt v1",
    summary: "1 finding",
    version: 1,
    pdf_artifact_id: null,
    xlsx_artifact_id: null,
    pdf_filename: null,
    xlsx_filename: null,
    finalized_at: "2026-08-17T00:00:00Z",
    released_at: null,
    ...overrides,
  } as Deliverable;
}

function finalizeButton(): HTMLButtonElement {
  return screen.getByRole("button", {
    name: /^(Finalize|Re-finalize|Finalizing…)$/,
  }) as HTMLButtonElement;
}

describe("DeliverableCard finalize gate", () => {
  it("enables finalize on an approved list", () => {
    render(
      <DeliverableCard
        serviceId="s1"
        capabilityListStatus="approved"
        deliverable={null}
        onChange={vi.fn()}
      />,
    );
    expect(finalizeButton()).not.toBeDisabled();
  });

  it("keeps finalize enabled after the list is RELEASED", () => {
    // The regression. The API accepts this call (`tech_debt.py` finalize gate
    // takes APPROVED or RELEASED, matching csf/zt/attack), so a disabled button
    // here is not a rule being enforced — it is the product refusing to do
    // something it is allowed to do, with no explanation on screen.
    render(
      <DeliverableCard
        serviceId="s1"
        capabilityListStatus="released"
        deliverable={deliverable({ released_at: "2026-08-17T01:00:00Z" })}
        onChange={vi.fn()}
      />,
    );
    expect(finalizeButton()).not.toBeDisabled();
  });

  it("disables finalize on a draft list", () => {
    render(
      <DeliverableCard
        serviceId="s1"
        capabilityListStatus="draft"
        deliverable={null}
        onChange={vi.fn()}
      />,
    );
    expect(finalizeButton()).toBeDisabled();
  });

  it("disables finalize when there is no list at all", () => {
    render(
      <DeliverableCard
        serviceId="s1"
        capabilityListStatus={null}
        deliverable={null}
        onChange={vi.fn()}
      />,
    );
    expect(finalizeButton()).toBeDisabled();
  });
});
