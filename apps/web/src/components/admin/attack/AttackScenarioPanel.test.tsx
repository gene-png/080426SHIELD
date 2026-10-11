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
  awaiting_review: 0,
  awaiting_review_text: null,
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
    run_error: null,
    today: ROLLUP,
    after: null,
    differences: [],
    techniques: [],
    dropped: null,
    not_reassessed: null,
    scored_higher: null,
    tools_added_since_base: null,
    ...over,
  };
}

const COMPLETED = {
  tools_added_since_base: 0,
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
      const body = await handler(url, init);
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
    // Q4: shown only where the api sends the sentence (it sends none at zero).
    expect(screen.getByTestId("scenario-today").textContent).not.toContain(
      "awaiting review",
    );
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

  it("states Q4's awaiting-review sentence beside the percentage it qualifies", async () => {
    const q4 =
      "1 technique lists tools awaiting review; it is scored as if those tools were not in place.";
    await startWith({
      ...COMPLETED,
      today: { ...ROLLUP, awaiting_review: 1, awaiting_review_text: q4 },
    });
    expect(screen.getByTestId("scenario-today").textContent).toContain(q4);
    expect(screen.getByTestId("scenario-after").textContent).not.toContain(q4);
  });

  it("(b2) above zero: says how many tools were added, in the plural, and marks their credit", async () => {
    await startWith({
      ...COMPLETED,
      tools_added_since_base: 2,
      differences: [
        {
          technique_code: "T1005",
          today: "gap",
          after: "partial",
          scored_higher: true,
          credited_added_tool: true,
        },
        {
          technique_code: "T1008",
          today: "covered",
          after: "partial",
          scored_higher: false,
          credited_added_tool: false,
        },
      ],
      techniques: [
        {
          technique_code: "T1005",
          detection_tools: ["XDR Tool"],
          prevention_tools: [],
          response_tools: [],
          ai_rows: [],
          credited_added_tools: ["XDR Tool"],
        },
        {
          technique_code: "T1066",
          detection_tools: ["XDR Tool"],
          prevention_tools: [],
          response_tools: [],
          ai_rows: [],
          credited_added_tools: ["XDR Tool"],
        },
      ],
    });
    expect(screen.getByTestId("attack-scenario-added").textContent).toBe(
      "2 tools were added to the client's list, or brought into scope, after the last confirmed assessment was approved. They were offered to the AI and may have taken over a removed tool's role.",
    );
    const marks = screen.getAllByTestId("attack-scenario-diff-added");
    expect(marks).toHaveLength(1);
    expect(marks[0].closest("tr")?.textContent).toContain("T1005");
    expect(
      screen.getByTestId("attack-scenario-added-unchanged").textContent,
    ).toBe("Also credited to an added tool, with no change in status: T1066.");
    expect(screen.queryByTestId("attack-scenario-added-unchecked")).toBeNull();
  });

  it("(b2) one tool: the singular", async () => {
    await startWith({ ...COMPLETED, tools_added_since_base: 1 });
    expect(screen.getByTestId("attack-scenario-added").textContent).toBe(
      "1 tool was added to the client's list, or brought into scope, after the last confirmed assessment was approved. It was offered to the AI and may have taken over a removed tool's role.",
    );
  });

  it("(b2) zero: says nothing about added tools", async () => {
    await startWith({ ...COMPLETED, tools_added_since_base: 0 });
    expect(screen.getByTestId("scenario-after")).toBeTruthy();
    expect(screen.queryByTestId("attack-scenario-added")).toBeNull();
    expect(screen.queryByTestId("attack-scenario-added-unchecked")).toBeNull();
  });

  it("(b2) could not be checked: says so, never a confident nothing", async () => {
    await startWith({ ...COMPLETED, tools_added_since_base: null });
    expect(
      screen.getByTestId("attack-scenario-added-unchecked").textContent,
    ).toBe(
      "Whether tools were added since the last confirmed assessment could not be checked for this client's list.",
    );
    expect(screen.queryByTestId("attack-scenario-added")).toBeNull();
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

  // --- review round 1 (web half) -------------------------------------------

  it("says why a run failed and offers to run the same what-if again", async () => {
    await startWith({
      state: "confirmed",
      run_status: "failed",
      ai_run_id: "r1",
      run_error: {
        reason: "scenario_discarded",
        message: "This what-if was set aside before the run finished.",
      },
    });
    expect(screen.getByTestId("attack-scenario-run-failed").textContent).toBe(
      "This what-if was set aside before the run finished.",
    );
    routes["POST /api/proxy/attack/scenarios/s1/run"] = () => ({
      run_id: "r2",
      status: "running",
    });
    routes["GET /api/proxy/attack/scenarios/s1"] = () => scenario(COMPLETED);
    fireEvent.click(
      screen.getByRole("button", { name: "Run AI analysis on these changes" }),
    );
    await screen.findByTestId("scenario-after");
    expect(screen.queryByTestId("attack-scenario-run-failed")).toBeNull();
  });

  it("offers no run on a what-if whose result stands, even beside a failed run", async () => {
    await startWith({
      ...COMPLETED,
      run_status: "failed",
      run_error: {
        reason: "scenario_already_run",
        message:
          "This what-if was analysed by another run while this one was working, so this run's result was not kept.",
      },
    });
    expect(screen.getByTestId("scenario-after")).toBeTruthy();
    expect(
      screen.queryByRole("button", {
        name: "Run AI analysis on these changes",
      }),
    ).toBeNull();
  });

  it("starts another what-if after a discard, without a reload", async () => {
    await startWith({});
    routes["POST /api/proxy/attack/scenarios/s1/discard"] = () =>
      scenario({ state: "discarded" });
    fireEvent.click(
      screen.getByRole("button", { name: "Discard this what-if" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Discard this what-if" }),
      ).toBeNull(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Start a new what-if" }),
    );
    routes[CREATE] = () => scenario({ id: "s2", removed: ["SIEM Tool"] });
    fireEvent.click(await screen.findByLabelText("SIEM Tool"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByTestId("attack-scenario");
    const creates = calls.filter(
      (c) =>
        c.init?.method === "POST" &&
        c.url === "/api/proxy/attack/services/svc/scenarios",
    );
    expect(JSON.parse(String(creates.at(-1)?.init?.body))).toEqual({
      removed: ["SIEM Tool"],
    });
  });

  it("after a reload, a running what-if is listed, opens, and is followed to its result", async () => {
    routes[LIST] = () => ({
      base: BASE,
      scenarios: [
        {
          id: "s9",
          state: "confirmed",
          removed: ["EDR Tool"],
          affected_count: 2,
          base_version: 3,
          created_at: "2026-10-03T06:00:00Z",
        },
        {
          id: "s8",
          state: "discarded",
          removed: ["SIEM Tool"],
          affected_count: 1,
          base_version: 3,
          created_at: "2026-10-03T05:00:00Z",
        },
      ],
    });
    let reads = 0;
    routes["GET /api/proxy/attack/scenarios/s9"] = () =>
      ++reads === 1
        ? scenario({
            id: "s9",
            state: "confirmed",
            run_status: "running",
            ai_run_id: "r9",
          })
        : scenario({ id: "s9", ...COMPLETED });
    render(<AttackScenarioPanel serviceId="svc" pollMs={5} />);
    const list = await screen.findByTestId("attack-scenario-list");
    // The discarded one is not offered.
    expect(list.textContent).toBe(
      "What-ifs on this serviceEDR Tool (compared with version 3)Open",
    );
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findByText("Running…")).toBeTruthy();
    await screen.findByTestId("scenario-after");
    expect(screen.queryByText("Running…")).toBeNull();
  });

  it("a poll still in flight never puts an older what-if back on screen", async () => {
    routes[LIST] = () => ({
      base: BASE,
      scenarios: [
        {
          id: "s9",
          state: "confirmed",
          removed: ["EDR Tool"],
          affected_count: 2,
          base_version: 3,
          created_at: "2026-10-03T06:00:00Z",
        },
      ],
    });
    let release: (v: unknown) => void = () => undefined;
    let reads = 0;
    routes["GET /api/proxy/attack/scenarios/s9"] = () => {
      reads += 1;
      if (reads === 1)
        return scenario({
          id: "s9",
          state: "confirmed",
          run_status: "running",
        });
      // The poll: held until the admin has moved on.
      return new Promise((resolve) => {
        release = resolve;
      });
    };
    render(<AttackScenarioPanel serviceId="svc" pollMs={5} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    await screen.findByText("Running…");
    await waitFor(() => expect(reads).toBe(2));
    fireEvent.click(
      screen.getByRole("button", { name: "Start a new what-if" }),
    );
    await screen.findByRole("button", { name: "Continue" });
    release(scenario({ id: "s9", state: "confirmed", run_status: "running" }));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByTestId("attack-scenario")).toBeNull();
    expect(screen.getByRole("button", { name: "Continue" })).toBeTruthy();
  });

  it("keeps polling after a failed read, and says so until one succeeds", async () => {
    routes[LIST] = () => ({
      base: BASE,
      scenarios: [
        {
          id: "s9",
          state: "confirmed",
          removed: ["EDR Tool"],
          affected_count: 2,
          base_version: 3,
          created_at: "2026-10-03T06:00:00Z",
        },
      ],
    });
    let reads = 0;
    routes["GET /api/proxy/attack/scenarios/s9"] = () => {
      reads += 1;
      if (reads === 1)
        return scenario({
          id: "s9",
          state: "confirmed",
          run_status: "running",
        });
      if (reads === 2) return { __status: 502 };
      return scenario({ id: "s9", ...COMPLETED });
    };
    render(<AttackScenarioPanel serviceId="svc" pollMs={5} />);
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    expect(
      (await screen.findByTestId("attack-scenario-poll-error")).textContent,
    ).toBe("The what-if's progress could not be read.");
    await screen.findByTestId("scenario-after");
    expect(screen.queryByTestId("attack-scenario-poll-error")).toBeNull();
  });

  it("never says a run that started could not be started", async () => {
    await startWith({});
    routes["POST /api/proxy/attack/scenarios/s1/run"] = () => ({
      run_id: "r1",
      status: "running",
    });
    routes["GET /api/proxy/attack/scenarios/s1"] = () => ({ __status: 502 });
    fireEvent.click(
      screen.getByRole("button", { name: "Run AI analysis on these changes" }),
    );
    expect(
      (await screen.findByTestId("attack-scenario-poll-error")).textContent,
    ).toBe("The AI analysis started, but its progress could not be read.");
    expect(screen.getByText("Running…")).toBeTruthy();
    expect(screen.queryByTestId("attack-scenario-error")).toBeNull();
  });
});
