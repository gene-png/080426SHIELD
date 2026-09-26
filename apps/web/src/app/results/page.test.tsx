/**
 * #556, review round 3 D: the Results page probes the Risk Register dashboard to
 * decide whether to link it, and rethrew anything but a 404. A WITHHELD register
 * answers a typed 409, which took the whole Results page down. It keeps its
 * link instead: the dashboard is where the client reads why it is withheld.
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
vi.mock("@/components/site/PublicHeader", () => ({ PublicHeader: () => null }));
vi.mock("@/components/site/PublicFooter", () => ({ PublicFooter: () => null }));

import ResultsPage from "./page";

const apiFetch = vi.mocked(api.apiFetch);

function probeAnswers(riskError: ApiError): void {
  apiFetch.mockImplementation(async (path: string) => {
    if (path === "/auth/me") return { role: "client", client_id: "c1" };
    if (path === "/clients/c1/deliverables") return { items: [] };
    throw riskError;
  });
}

describe("Results page, Risk Register probe (#556)", () => {
  it("keeps the Risk Register link for a withheld register", async () => {
    probeAnswers(
      new ApiError(409, "corr-1", {
        error: {
          code: 409,
          correlation_id: "corr-1",
          reason: "attack_catalog_mismatch",
          message: "withheld",
        },
      }),
    );
    render(await ResultsPage());
    expect(
      screen.getByRole("link", { name: /View Risk Register dashboard/ }),
    ).toBeInTheDocument();
  });

  it("shows no link when no register is finalized", async () => {
    probeAnswers(new ApiError(404, "corr-1", { error: { code: 404 } }));
    render(await ResultsPage());
    expect(
      screen.queryByRole("link", { name: /View Risk Register dashboard/ }),
    ).not.toBeInTheDocument();
  });
});
