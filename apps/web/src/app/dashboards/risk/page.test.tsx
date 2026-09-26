/**
 * #556, review round 3 D: a finalized Risk Register built from an ATT&CK
 * assessment on another catalog is withheld by the API (typed 409). The page
 * must render that sentence, not rethrow it into Next's error page. Tested
 * through the PAGE, because the defect is which statuses the page handles.
 */
import "@testing-library/jest-dom/vitest";

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
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
}));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/components/dashboards/risk/RiskDashboard", () => ({
  RiskDashboard: () => <div>dashboard</div>,
}));

import RiskDashboardPage from "./page";

const apiFetch = vi.mocked(api.apiFetch);

const WITHHELD =
  "This Risk Register was built from an ATT&CK coverage report produced against an earlier version of the ATT&CK framework than the current one (v19.2), so it is withheld.";

function refusal(reason: string, message: string): ApiError {
  return new ApiError(409, "corr-1", {
    error: { code: 409, correlation_id: "corr-1", reason, message },
  });
}

function answer(dashboardError: ApiError): void {
  apiFetch.mockImplementation(async (path: string) => {
    if (path === "/auth/me") return { role: "client", client_id: "c1" };
    throw dashboardError;
  });
}

describe("Risk Register client dashboard page, withheld register (#556)", () => {
  it("renders the API's withholding sentence instead of crashing", async () => {
    answer(refusal("attack_catalog_mismatch", WITHHELD));
    render(await RiskDashboardPage());
    expect(
      screen.getByRole("heading", { name: "Risk Register withheld" }),
    ).toBeInTheDocument();
    expect(screen.getByText(WITHHELD)).toBeInTheDocument();
  });

  it("still rethrows a 409 it has no copy for", async () => {
    answer(refusal("something_else", "Other."));
    await expect(RiskDashboardPage()).rejects.toBeInstanceOf(ApiError);
  });
});
