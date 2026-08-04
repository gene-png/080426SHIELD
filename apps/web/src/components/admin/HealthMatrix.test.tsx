import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthMatrix } from "./HealthMatrix";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockReady(body: unknown): void {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const allGreen = {
  status: "ok",
  ready: true,
  version: "3.3.0",
  offenders: [],
  checks: {
    db: { status: "ok", required: true, detail: "SELECT 1 ok" },
    redis: { status: "ok", required: true, detail: "PING ok" },
    minio: { status: "ok", required: true, detail: "bucket reachable" },
    keycloak: { status: "dormant", required: false, detail: "dormant in v1" },
    llm: { status: "ok", required: false, detail: "fixture mode" },
  },
};

describe("HealthMatrix", () => {
  it("renders every dependency row and an all-green overall badge", async () => {
    mockReady(allGreen);
    render(<HealthMatrix />);
    await waitFor(() =>
      expect(screen.getByText(/all systems ready/i)).toBeInTheDocument(),
    );
    for (const dep of ["db", "redis", "minio", "keycloak", "llm"]) {
      expect(screen.getByText(dep)).toBeInTheDocument();
    }
  });

  it("shows a degraded badge and names the offender when a required dep is down", async () => {
    mockReady({
      ...allGreen,
      status: "degraded",
      ready: false,
      offenders: ["redis"],
      checks: {
        ...allGreen.checks,
        redis: { status: "down", required: true, detail: "ConnectionError" },
      },
    });
    render(<HealthMatrix />);
    await waitFor(() =>
      expect(screen.getByText(/degraded/i)).toBeInTheDocument(),
    );
    // "redis" appears both in the offender badge and as the row label.
    expect(screen.getAllByText(/redis/).length).toBeGreaterThan(0);
    expect(screen.getByText(/ConnectionError/)).toBeInTheDocument();
  });
});
