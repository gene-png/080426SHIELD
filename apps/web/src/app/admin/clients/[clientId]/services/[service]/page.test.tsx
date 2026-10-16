/**
 * T6: a service URL with no section. Every service kind goes to its Overview;
 * the Risk Register (no sections yet) renders its existing dashboard, whose own
 * `?client` must agree with the path's client.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  A,
  B,
  baseWorld,
  installFakeApi,
  NotFoundSignal,
  RedirectSignal,
} from "../../../fake-api.testkit";

vi.mock("@/lib/auth/options", () => ({
  auth: async () => ({ role: "admin", accessToken: "tok" }),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
}));
vi.mock("next/navigation", async () => {
  const kit = await import("../../../fake-api.testkit");
  return {
    notFound: () => {
      throw new kit.NotFoundSignal();
    },
    redirect: (url: string) => {
      throw new kit.RedirectSignal(url);
    },
  };
});
vi.mock("@/components/admin/risk/RiskRegisterDashboard", () => ({
  RiskRegisterDashboard: () => <div data-testid="risk-dashboard" />,
}));

import ServicePage from "./page";

function call(
  clientId: string,
  service: string,
  query: Record<string, string> = {},
) {
  return ServicePage({
    params: Promise.resolve({ clientId, service }),
    searchParams: Promise.resolve(query),
  });
}

beforeEach(() => {
  installFakeApi(baseWorld());
});

describe("service URL with no section", () => {
  it("goes to Overview, keeping the service id", async () => {
    await expect(call(A, "tech-debt", { service: "td-a" })).rejects.toEqual(
      new RedirectSignal(
        `/admin/clients/${A}/services/tech-debt/overview?service=td-a`,
      ),
    );
  });

  it("goes to Overview without an id when none was given", async () => {
    await expect(call(A, "csf")).rejects.toEqual(
      new RedirectSignal(`/admin/clients/${A}/services/csf/overview`),
    );
  });

  it("refuses an unknown service slug", async () => {
    await expect(call(A, "bogus")).rejects.toBeInstanceOf(NotFoundSignal);
  });
});

describe("Risk Register", () => {
  it("adds ?client naming the path's client", async () => {
    await expect(call(A, "risk-register")).rejects.toEqual(
      new RedirectSignal(
        `/admin/clients/${A}/services/risk-register?client=${A}`,
      ),
    );
  });

  it("follows the dashboard's own picker to the other client's path", async () => {
    await expect(call(A, "risk-register", { client: B })).rejects.toEqual(
      new RedirectSignal(
        `/admin/clients/${B}/services/risk-register?client=${B}`,
      ),
    );
  });

  it("renders the existing dashboard when the two agree", async () => {
    render(await call(A, "risk-register", { client: A }));
    expect(screen.getByTestId("risk-dashboard")).toBeInTheDocument();
  });

  it("refuses an unknown client", async () => {
    await expect(
      call("client-z", "risk-register", { client: "client-z" }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });
});
