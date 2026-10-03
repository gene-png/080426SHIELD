import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttackScenarioPanel } from "./AttackScenarioPanel";

// The guard's own behaviour is pinned by RunAiGuard.test.tsx; here a click
// goes straight through, acknowledged offline.
vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    onProceed,
    children,
  }: {
    onProceed: (s: "offline") => void;
    children: (p: {
      onClick: () => void;
      statusUnknown: boolean;
    }) => React.ReactNode;
  }) => children({ onClick: () => onProceed("offline"), statusUnknown: false }),
}));

const BASE = {
  assessment_id: "a1",
  version: 3,
  approved_at: "2026-10-01T12:00:00Z",
  tools: ["EDR Tool", "SIEM Tool"],
};

const ROLLUP = {
  coverage_pct: 50,
  covered: 1,
  partial: 2,
  gap: 0,
  not_applicable: 0,
  pending_review: 0,
  scored_count: 3,
  catalogue_count: 3,
  unable_to_determine: 0,
  outside_control_surface: 1,
};

function scenario(over: Record<string, unknown> = {}) {
  return {
    id: "s1",
    service_id: "svc",
    state: "draft",
    removed: ["EDR Tool"],
    affected_codes: ["T1005", "T1008"],
    base_assessment_id: "a1",
    base_version: 3,
    base_approved_at: "2026-10-01T12:00:00Z",
    stale: false,
    analysis_available: true,
    ai_run_id: null,
    run_status: null,
    today: ROLLUP,
    after: null,
    differences: [],
    techniques: [],
    dropped: null,
    not_reassessed: null,
    scored_higher: null,
    ...over,
  };
}

const COMPLETED = {
  state: "confirmed",
  run_status: "completed",
  ai_run_id: "r1",
  after: ROLLUP,
  dropped: {},
  not_reassessed: [],
};

type Route = (url: string, init?: RequestInit) => unknown;

let routes: Record<string, Route>;
let calls: { url: string; init?: RequestInit }[];

beforeEach(() => {
  calls = [];
  routes = {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const key = `${init?.method ?? "GET"} ${url}`;
      const handler = routes[key];
      if (!handler) throw new Error(`unexpected ${key}`);
      const body = handler(url, init);
      const status =
        typeof body === "object" && body !== null && "__status" in body
          ? (body as { __status: number }).__status
          : 200;
      return new Response(JSON.stringify(body), { status });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LIST = "GET /api/proxy/attack/services/svc/scenarios";
const CREATE = "POST /api/proxy/attack/services/svc/scenarios";

async function startWith(s: Record<string, unknown>): Promise<void> {
  routes[LIST] = () => ({ base: BASE, scenarios: [] });
  routes[CREATE] = () => scenario(s);
  render(<AttackScenarioPanel serviceId="svc" />);
  fireEvent.click(await screen.findByLabelText("EDR Tool"));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByTestId("attack-scenario");
}

describe("AttackScenarioPanel", () => {
  it("says what to do when there is no confirmed assessment", async () => {
    routes[LIST] = () => ({ base: null, scenarios: [] });
    render(<AttackScenarioPanel serviceId="svc" />);
    expect(
      (await screen.findByTestId("attack-scenario-no-base")).textContent,
    ).toBe(
      "There is no confirmed assessment to compare with yet. Approve the ATT&CK assessment and review every technique in its review queue, then try again.",
    );
    expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
  });

  it("starts a what-if with the picked tools and names what it affects", async () => {
    await startWith({});
    const create = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(create?.init?.body))).toEqual({
      removed: ["EDR Tool"],
    });
    expect(screen.getByTestId("attack-scenario-affected").textContent).toBe(
      "2 techniques use these tools and will be re-assessed.",
    );
  });

  it("names one affected technique in the singular", async () => {
    await startWith({ affected_codes: ["T1005"] });
    expect(screen.getByTestId("attack-scenario-affected").textContent).toBe(
      "1 technique uses these tools and will be re-assessed.",
    );
  });

  it("says analysis is unavailable instead of offering a run that is refused", async () => {
    await startWith({ analysis_available: false });
    expect(screen.getByTestId("attack-scenario-unavailable").textContent).toBe(
      "AI analysis for what-ifs is not available yet.",
    );
    expect(
      screen.queryByRole("button", {
        name: "Run AI analysis on these changes",
      }),
    ).toBeNull();
  });

  it("runs the analysis with the acknowledged mode", async () => {
    await startWith({});
    routes["POST /api/proxy/attack/scenarios/s1/run"] = () => ({
      run_id: "r1",
      status: "running",
    });
    routes["GET /api/proxy/attack/scenarios/s1"] = () =>
      scenario({ ...COMPLETED });
    fireEvent.click(
      screen.getByRole("button", { name: "Run AI analysis on these changes" }),
    );
    await screen.findByTestId("scenario-after");
    const run = calls.find((c) => c.url.endsWith("/s1/run"));
    expect(JSON.parse(String(run?.init?.body))).toEqual({ serves: "offline" });
    expect(screen.getByText("With these changes")).toBeTruthy();
    // #554: the outside counts beside each percentage, never dropped at zero.
    expect(screen.getByTestId("scenario-after").textContent).toContain(
      "Not verified 0, Outside control surface 1.",
    );
    expect(screen.getByTestId("scenario-today").textContent).toContain(
      "Not verified 0, Outside control surface 1.",
    );
  });

  it("warns, in the singular, when one technique would score higher, and marks only it", async () => {
    await startWith({
      ...COMPLETED,
      scored_higher: 1,
      differences: [
        {
          technique_code: "T1005",
          today: "covered",
          after: "partial",
          scored_higher: false,
        },
        {
          technique_code: "T1008",
          today: "partial",
          after: "covered",
          scored_higher: true,
        },
      ],
    });
    expect(screen.getByTestId("attack-scenario-higher").textContent).toBe(
      "1 technique would score higher than today, because the AI credited a remaining tool the last confirmed assessment did not. Check it before relying on the result.",
    );
    const marks = screen.getAllByTestId("attack-scenario-diff-higher");
    expect(marks).toHaveLength(1);
    expect(marks[0].closest("tr")?.textContent).toContain("T1008");
  });

  it("warns in the plural when several would score higher", async () => {
    await startWith({ ...COMPLETED, scored_higher: 2 });
    expect(screen.getByTestId("attack-scenario-higher").textContent).toBe(
      "2 techniques would score higher than today, because the AI credited a remaining tool the last confirmed assessment did not. Check these before relying on the result.",
    );
  });

  it("says nothing about scoring higher when nothing does", async () => {
    await startWith({ ...COMPLETED, scored_higher: 0 });
    expect(screen.getByTestId("scenario-after")).toBeTruthy();
    expect(screen.queryByTestId("attack-scenario-higher")).toBeNull();
  });

  it("discloses techniques not re-assessed and suggestions set aside", async () => {
    await startWith({
      ...COMPLETED,
      not_reassessed: ["T1005"],
      dropped: {
        tool_outside_change: 2,
        tool_unconfirmed: 1,
        function_not_lost: 3,
      },
    });
    expect(
      screen.getByTestId("attack-scenario-not-reassessed").textContent,
    ).toBe(
      "1 technique could not be re-assessed because the AI did not answer for it. It shows the removal alone: the removed tools are taken out and nothing else changes.",
    );
    expect(
      screen
        .getAllByTestId("attack-scenario-dropped")
        .map((p) => p.textContent),
    ).toEqual([
      "2 AI suggestions were set aside because they named a tool or a technique outside these changes.",
      "1 AI suggestion was set aside because the tool it named could not be matched exactly to one of the client's tools.",
      "3 AI suggestions were set aside because they credited Detect, Prevent or Respond where these changes took nothing away.",
    ]);
  });

  it("names a single suggestion crediting an unaffected function in the singular", async () => {
    await startWith({ ...COMPLETED, dropped: { function_not_lost: 1 } });
    expect(
      screen
        .getAllByTestId("attack-scenario-dropped")
        .map((p) => p.textContent),
    ).toEqual([
      "1 AI suggestion was set aside because it credited Detect, Prevent or Respond where these changes took nothing away.",
    ]);
  });

  it("offers to run a stale what-if again against the newer assessment", async () => {
    await startWith({ stale: true });
    expect(screen.getByTestId("attack-scenario-stale").textContent).toContain(
      "This what-if was compared with version 3. A newer assessment has been confirmed since; run it again to compare with that one.",
    );
    expect(
      screen.queryByRole("button", {
        name: "Run AI analysis on these changes",
      }),
    ).toBeNull();
    routes[CREATE] = () => scenario({ id: "s2" });
    const before = calls.filter((c) => c.init?.method === "POST").length;
    fireEvent.click(screen.getByRole("button", { name: "Run it again" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.init?.method === "POST").length).toBe(
        before + 1,
      ),
    );
    const again = calls.filter((c) => c.init?.method === "POST").at(-1);
    expect(again?.url).toBe("/api/proxy/attack/services/svc/scenarios");
    expect(JSON.parse(String(again?.init?.body))).toEqual({
      removed: ["EDR Tool"],
    });
  });

  it("shows the server's typed refusal", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    routes[CREATE] = () => ({
      __status: 422,
      error: {
        reason: "scenario_empty_change",
        message: "Choose at least one tool to remove.",
      },
    });
    render(<AttackScenarioPanel serviceId="svc" />);
    fireEvent.click(await screen.findByRole("button", { name: "Continue" }));
    expect(
      (await screen.findByTestId("attack-scenario-error")).textContent,
    ).toBe("Choose at least one tool to remove.");
  });
});
