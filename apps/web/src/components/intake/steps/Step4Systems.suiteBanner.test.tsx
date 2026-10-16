import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Step4Systems } from "./Step4Systems";
import type { IntakeStateResponse, ServiceType } from "@/lib/intake/types";

/**
 * #1170: the suite-listing banner (#1058, TD-2) moved to the Notes and
 * artifacts step; its copy is pinned in `Step5Notes.suiteBanner.test.tsx`.
 * Systems shows it for no selection, including the ones that show it there.
 */

const HEADING = "List each product separately, not as a suite.";

function stateWith(services: ServiceType[] | null): IntakeStateResponse {
  return {
    client: { prompting_context: "", service_interests: services },
  } as unknown as IntakeStateResponse;
}

function renderStep(services: ServiceType[] | null) {
  return render(<Step4Systems state={stateWith(services)} onSave={vi.fn()} />);
}

describe("Step4Systems suite-listing banner", () => {
  it.each([
    [["tech_debt"] as ServiceType[]],
    [["attack_coverage"] as ServiceType[]],
    [["nist_csf", "attack_coverage", "tech_debt"] as ServiceType[]],
    [["nist_csf", "zero_trust_cisa"] as ServiceType[]],
    [[]],
    [null],
  ])("shows no banner for %j", (services) => {
    renderStep(services);
    // The step itself rendered, so the absence below is not vacuous.
    expect(screen.getByLabelText("Systems and context")).toBeVisible();
    expect(screen.queryByRole("heading", { name: HEADING })).toBeNull();
  });
});
