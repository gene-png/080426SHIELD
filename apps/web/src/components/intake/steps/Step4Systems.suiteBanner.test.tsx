import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Step4Systems } from "./Step4Systems";
import type { IntakeStateResponse, ServiceType } from "@/lib/intake/types";

/**
 * #1058 (TD-2): Step 4 tells a client picking Tech Debt or ATT&CK to list each
 * product separately rather than as a suite. Expected copy is Gene's draft on
 * #736 (comment 6115250609), copied from the comment, not from the component;
 * the MITRE variant per the ruling in 6115345112.
 */

const HEADING = "List each product separately, not as a suite.";
const TECH_DEBT_LINE =
  "Many licenses are suites that bundle several products. Please list every product, module or capability you use on its own line, not just the suite name. Each one does a different job, and we assess each job separately.";
const MITRE_LINE =
  "Many security tools come as suites. Please list every product, module or capability that detects, prevents or responds to threats on its own line, not just the suite name. Each one does a different job, and we assess each job separately.";
const EXAMPLE =
  "Example: Microsoft 365 G5 is one license, but it includes separate products such as Microsoft Defender for Endpoint (protects computers and servers), Microsoft Entra ID P2 (manages sign-in and identity) and Microsoft Purview (protects and classifies sensitive data). List each one you use, and say whether it is in use or purchased but not deployed.";
const CONTACT = "Questions? Contact your Kentro representative.";

function stateWith(services: ServiceType[] | null): IntakeStateResponse {
  return {
    client: { prompting_context: "", service_interests: services },
  } as unknown as IntakeStateResponse;
}

function renderStep(services: ServiceType[] | null) {
  return render(<Step4Systems state={stateWith(services)} onSave={vi.fn()} />);
}

function banner(): HTMLElement {
  const heading = screen.getByRole("heading", { level: 4, name: HEADING });
  const region = heading.closest("section");
  if (!region) throw new Error("banner heading is not inside a section");
  return region;
}

function paragraphs(region: HTMLElement): string[] {
  return within(region)
    .getAllByText((_, el) => el?.tagName === "P")
    .map((p) => p.textContent ?? "");
}

describe("Step4Systems suite-listing banner", () => {
  it("shows the Tech Debt text when Tech Debt is selected", () => {
    renderStep(["tech_debt"]);
    expect(paragraphs(banner())).toEqual([TECH_DEBT_LINE, EXAMPLE, CONTACT]);
  });

  it("shows the MITRE text when ATT&CK is selected", () => {
    renderStep(["attack_coverage"]);
    expect(paragraphs(banner())).toEqual([MITRE_LINE, EXAMPLE, CONTACT]);
  });

  it("shows ONE banner, with the Tech Debt text, when both are selected", () => {
    renderStep(["nist_csf", "attack_coverage", "tech_debt"]);
    expect(
      screen.getAllByRole("heading", { level: 4, name: HEADING }),
    ).toHaveLength(1);
    expect(paragraphs(banner())).toEqual([TECH_DEBT_LINE, EXAMPLE, CONTACT]);
  });

  it.each([[["nist_csf", "zero_trust_cisa"] as ServiceType[]], [[]], [null]])(
    "shows no banner for %j",
    (services) => {
      renderStep(services);
      // The step itself rendered, so the absence below is not vacuous.
      expect(screen.getByLabelText("Systems and context")).toBeVisible();
      expect(screen.queryByRole("heading", { name: HEADING })).toBeNull();
    },
  );
});
