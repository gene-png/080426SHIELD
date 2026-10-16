import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({
  pathname: "/admin/clients/c-1",
  search: new URLSearchParams(),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useSearchParams: () => nav.search,
}));
vi.mock("./ClientNavPicker", () => ({
  ClientNavPicker: ({ currentId }: { currentId: string | null }) => (
    <div data-testid="picker">{currentId}</div>
  ),
}));

import { ClientRail, type RailService } from "./ClientRail";

function svc(
  service_id: string,
  service_type: RailService["service_type"],
  created_at: string,
  status = "in_progress",
): RailService {
  return { service_id, service_type, status, created_at };
}

function rail(services: RailService[]): HTMLElement {
  render(
    <ClientRail
      client={{ id: "c-1", label: "Alpha Corp" }}
      services={services}
    />,
  );
  return screen.getByRole("navigation", { name: "Client services" });
}

function linkNames(el: HTMLElement): string[] {
  return within(el)
    .getAllByRole("link")
    .map((a) => a.textContent ?? "");
}

beforeEach(() => {
  nav.pathname = "/admin/clients/c-1";
  nav.search = new URLSearchParams();
});

describe("ClientRail", () => {
  it("shows the client's name and the picker set to it", () => {
    rail([]);
    expect(screen.getByText("Alpha Corp")).toBeInTheDocument();
    expect(screen.getByTestId("picker")).toHaveTextContent("c-1");
  });

  it("lists open services in the fixed order, then the Risk Register", () => {
    const el = rail([
      svc("csf-1", "nist_csf", "2026-09-01T00:00:00Z"),
      svc("td-1", "tech_debt", "2026-09-02T00:00:00Z"),
      svc("ztd-1", "zero_trust_dod", "2026-09-03T00:00:00Z"),
      svc("atk-1", "attack_coverage", "2026-09-04T00:00:00Z"),
      svc("ztc-1", "zero_trust_cisa", "2026-09-05T00:00:00Z"),
    ]);
    expect(linkNames(el)).toEqual([
      "Technical Debt Review",
      "MITRE ATT&CK Coverage",
      "Zero Trust (CISA ZTMM 2.0)",
      "Zero Trust (DoD ZTRA)",
      "NIST CSF 2.0",
      "Risk Register",
    ]);
    expect(
      within(el)
        .getByRole("link", { name: "NIST CSF 2.0" })
        .getAttribute("href"),
    ).toBe("/admin/clients/c-1/services/csf/overview?service=csf-1");
    expect(
      within(el)
        .getByRole("link", { name: "Risk Register" })
        .getAttribute("href"),
    ).toBe("/admin/clients/c-1/services/risk-register");
  });

  it("leaves archived services out", () => {
    const el = rail([
      svc("td-1", "tech_debt", "2026-09-02T00:00:00Z", "archived"),
      svc("csf-1", "nist_csf", "2026-09-01T00:00:00Z"),
    ]);
    expect(linkNames(el)).toEqual(["NIST CSF 2.0", "Risk Register"]);
  });

  it("tells two services of one kind apart by start date, oldest first", () => {
    const el = rail([
      svc("td-2", "tech_debt", "2026-10-01T09:00:00Z"),
      svc("td-1", "tech_debt", "2026-09-02T09:00:00Z"),
    ]);
    expect(linkNames(el)).toEqual([
      "Technical Debt Review, started 2026-09-02",
      "Technical Debt Review, started 2026-10-01",
      "Risk Register",
    ]);
  });

  it("says when no service is open, with the intake queue link", () => {
    const el = rail([]);
    expect(
      within(el).getByText("No services are open for this client yet."),
    ).toBeInTheDocument();
    expect(
      within(el).getByRole("link", { name: "Open the intake queue" }),
    ).toHaveAttribute("href", "/admin/queue/c-1");
    expect(
      within(el).getByRole("link", { name: "Risk Register" }),
    ).toBeTruthy();
  });

  it("marks the service on screen as current, by id not by kind", () => {
    nav.pathname = "/admin/clients/c-1/services/tech-debt/review";
    nav.search = new URLSearchParams("service=td-2");
    const el = rail([
      svc("td-1", "tech_debt", "2026-09-02T09:00:00Z"),
      svc("td-2", "tech_debt", "2026-10-01T09:00:00Z"),
    ]);
    expect(
      within(el).getByRole("link", {
        name: "Technical Debt Review, started 2026-10-01",
      }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(el).getByRole("link", {
        name: "Technical Debt Review, started 2026-09-02",
      }),
    ).not.toHaveAttribute("aria-current");
  });

  it("marks the Risk Register current on its route", () => {
    nav.pathname = "/admin/clients/c-1/services/risk-register";
    const el = rail([]);
    expect(
      within(el).getByRole("link", { name: "Risk Register" }),
    ).toHaveAttribute("aria-current", "page");
  });
});
