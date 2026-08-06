import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SharedServiceDefaults } from "./SharedServiceDefaults";
import type { ServiceRequestInput, ServiceType } from "@/lib/intake/types";

/**
 * UX finding 8: a client picking four services typed the same deadline and the
 * same paragraph four times.
 *
 * The rule that matters is that applying fills BLANKS ONLY. A shared value that
 * overwrote a deadline someone deliberately set for one service would destroy
 * the override rather than provide a default — the opposite of what the finding
 * asks for.
 */

const THREE: ServiceType[] = ["tech_debt", "nist_csf", "attack_coverage"];

function inputs(
  partial: Partial<Record<ServiceType, ServiceRequestInput>> = {},
): Record<ServiceType, ServiceRequestInput> {
  return partial as Record<ServiceType, ServiceRequestInput>;
}

describe("SharedServiceDefaults", () => {
  it("does not render for a single service", () => {
    // Nothing to share: the per-service field is already the shortest path.
    const { container } = render(
      <SharedServiceDefaults
        services={["tech_debt"]}
        serviceInputs={inputs()}
        onApply={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("cannot be applied until there is something to apply", () => {
    render(
      <SharedServiceDefaults
        services={THREE}
        serviceInputs={inputs()}
        onApply={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Apply to my services" }),
    ).toBeDisabled();
  });

  it("counts only the services that would actually be filled", () => {
    render(
      <SharedServiceDefaults
        services={THREE}
        serviceInputs={inputs({
          // This one already has a deadline, so it is not a blank to fill.
          nist_csf: {
            service_type: "nist_csf",
            deadline: "2027-01-01T00:00:00Z",
          },
        })}
        onApply={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Target deadline/), {
      target: { value: "2027-06-30" },
    });

    // Three services, one already set → two blanks.
    expect(screen.getByRole("status")).toHaveTextContent("2 deadlines");
  });

  it("reports what it did, naming the count", () => {
    const onApply = vi.fn();
    render(
      <SharedServiceDefaults
        services={THREE}
        serviceInputs={inputs()}
        onApply={onApply}
      />,
    );

    fireEvent.change(screen.getByLabelText(/General context/), {
      target: { value: "FedRAMP Moderate" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Apply to my services" }),
    );

    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({ notes: "FedRAMP Moderate" }),
    );
    // A button that fills fields further down the page — several of them
    // collapsed — is indistinguishable from one that did nothing unless it says
    // so.
    expect(screen.getByRole("status")).toHaveTextContent(
      "Applied context on 3 services.",
    );
  });

  it("treats whitespace-only context as nothing to apply", () => {
    render(
      <SharedServiceDefaults
        services={THREE}
        serviceInputs={inputs()}
        onApply={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText(/General context/), {
      target: { value: "   " },
    });
    expect(
      screen.getByRole("button", { name: "Apply to my services" }),
    ).toBeDisabled();
  });
});
