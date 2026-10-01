import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { EnterpriseProfile } from "@/lib/csf/types";

import type * as React from "react";

import { CsfPlaybookPanel } from "./CsfPlaybookPanel";

/**
 * #550: a CSF Run AI whose answer the proxy never saw is not a failed run. The
 * panel says the outcome is unknown, names where to check, and keeps Run AI
 * off for the rest of the page's life.
 */

vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class CsfProxyError extends Error {},
  fetchEnterpriseProfile: vi.fn(),
  seedProfiles: vi.fn(),
  runCsfAi: vi.fn(),
  exportPlaybook: vi.fn(),
}));
vi.mock("../AiPreviewButton", () => ({ AiPreviewButton: () => null }));
vi.mock("./CsfDimensionEditor", () => ({ CsfDimensionEditor: () => null }));
vi.mock("./CsfGapActionEditor", () => ({ CsfGapActionEditor: () => null }));
vi.mock("../RunAiGuard", () => ({
  RunAiGuard: ({
    onProceed,
    children,
  }: {
    onProceed: () => void;
    children: (props: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: onProceed }),
}));

/** What `lib/csf/client.ts` throws: its error class, envelope on `.payload`. */
function proxyRefusal(status: number, reason: string, message: string): Error {
  const ProxyError = csfClient.CsfProxyError as unknown as new (
    m: string,
  ) => Error;
  return Object.assign(new ProxyError(`CSF proxy ${status}`), {
    status,
    payload: { error: { code: status, reason, message } },
  });
}

const OUTCOME_UNKNOWN = proxyRefusal(
  504,
  "upstream_outcome_unknown",
  "We couldn't confirm whether this finished. It may still complete; check before trying again.",
);

const COPY =
  "We couldn't confirm whether the AI run finished. It may still complete and fill in dimension scores. Reload the page later and check the dimension scores in Full Playbook — Working Profiles before running it again. Run AI stays off on this page until you reload.";

const RUN = "Run AI (csf_score)";

beforeEach(() => {
  vi.mocked(csfClient.fetchEnterpriseProfile).mockResolvedValue({
    tiers_in_use: ["moderate"],
    subcategories: [
      {
        subcategory_code: "GV.OC-01",
        name: "GV.OC-01 outcome",
        function: "GV",
        tier_levels: { moderate: 2 },
        enterprise_level: 2,
        rollup_rule: 1,
        target_level: 3,
        gap: false,
        priority: null,
      },
    ],
  } as EnterpriseProfile);
  vi.mocked(csfClient.runCsfAi).mockReset();
});

async function runAiRejectingWith(err: Error): Promise<void> {
  vi.mocked(csfClient.runCsfAi).mockRejectedValueOnce(err);
  render(<CsfPlaybookPanel serviceId="svc-550-csf" />);
  const button = await screen.findByRole("button", { name: RUN });
  expect(button).toBeEnabled();
  fireEvent.click(button);
}

describe("CsfPlaybookPanel, a Run AI whose outcome is unknown (#550)", () => {
  it("says where to check rather than that the run failed, and keeps Run AI off", async () => {
    await runAiRejectingWith(OUTCOME_UNKNOWN);

    expect(await screen.findByText(COPY)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: RUN })).toBeDisabled();
  });

  it("leaves Run AI on after a refusal the api DID send", async () => {
    await runAiRejectingWith(
      proxyRefusal(409, "assessment_not_draft", "Not a draft."),
    );

    expect(await screen.findByText("Not a draft.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: RUN })).toBeEnabled();
    expect(screen.queryByText(COPY)).not.toBeInTheDocument();
  });
});
