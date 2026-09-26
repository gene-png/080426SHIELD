/**
 * #556: the client dashboard of an ATT&CK report scored against another catalog.
 * The API answers a typed 409 (`attack_catalog_mismatch`). This page used to
 * handle only 404 and rethrow everything else, so that 409 reached Next's
 * unhandled error page and the API's sentence never reached a screen. Tested
 * through the PAGE, because the defect was which statuses the page handles.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiFetch: vi.fn() };
});
vi.mock("@/lib/auth/options", () => ({
  auth: async () => ({ accessToken: "token" }),
}));
vi.mock("@/lib/dashboards/resolveClient", () => ({
  resolveDashboardClientId: async () => "client-1",
}));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/components/dashboards/attack/AttackDashboard", () => ({
  AttackDashboard: () => <div>dashboard</div>,
}));

import AttackDashboardPage from "./page";

const apiFetch = vi.mocked(api.apiFetch);

// What the API sends, as `_handle_http_exception` envelopes it.
const WITHHELD =
  "This ATT&CK coverage report was produced against an earlier version of the ATT&CK framework than the current one (v19.2), so its figures are withheld.";

function refusal(status: number, reason: string, message: string): ApiError {
  return new ApiError(status, "corr-1", {
    error: { code: "conflict", correlation_id: "corr-1", reason, message },
  });
}

async function renderPage(): Promise<void> {
  render(
    await AttackDashboardPage({
      params: Promise.resolve({ serviceId: "svc-1" }),
    }),
  );
}

describe("ATT&CK client dashboard page, stale catalog (#556)", () => {
  it("renders the API's withholding sentence instead of crashing", async () => {
    apiFetch.mockRejectedValue(
      refusal(409, "attack_catalog_mismatch", WITHHELD),
    );
    await renderPage();
    expect(
      screen.getByRole("heading", { name: "Dashboard withheld" }),
    ).toBeTruthy();
    expect(screen.getByText(WITHHELD)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Back to results/ })).toBeTruthy();
  });

  it("still rethrows a 409 it has no copy for", async () => {
    apiFetch.mockRejectedValue(refusal(409, "something_else", "Other."));
    await expect(
      AttackDashboardPage({ params: Promise.resolve({ serviceId: "svc-1" }) }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
