import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttackScenarioPanel } from "./AttackScenarioPanel";

/**
 * #802 slice B: tools the client doesn't have. Copy B1-B14 approved by the
 * advisor at 14:58Z; every sentence here is asserted byte for byte.
 */

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

const XDR = {
  name: "XDR Suite",
  vendor: "Vendor X",
  category: null,
  security_functions: ["detect", "prevent"],
};

function scenario(over: Record<string, unknown> = {}) {
  return {
    id: "s1",
    service_id: "svc",
    state: "draft",
    removed: [],
    added: [XDR],
    affected_codes: ["T1005", "T1008"],
    affected_by_removal: 0,
    affected_by_addition_only: 2,
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
    higher_with_added: null,
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
  scored_higher: 0,
  higher_with_added: 0,
};

let routes: Record<string, (url: string, init?: RequestInit) => unknown>;
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
      return new Response(JSON.stringify(await handler(url, init)), {
        status: 200,
      });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LIST = "GET /api/proxy/attack/services/svc/scenarios";
const CREATE = "POST /api/proxy/attack/services/svc/scenarios";

function posts(): { removed: string[]; added?: unknown[] }[] {
  return calls
    .filter((c) => c.init?.method === "POST")
    .map((c) => JSON.parse(String(c.init?.body)));
}

async function show(s: Record<string, unknown>): Promise<void> {
  routes[LIST] = () => ({ base: BASE, scenarios: [] });
  routes[CREATE] = () => scenario(s);
  render(<AttackScenarioPanel serviceId="svc" />);
  fireEvent.click(await screen.findByRole("button", { name: "Add a tool" }));
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "XDR Suite" },
  });
  fireEvent.click(screen.getByLabelText("Detect"));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByTestId("attack-scenario");
}

describe("AttackScenarioPanel, tools to add (slice B)", () => {
  it("sends the tools to add, typed by the admin, in D/P/R order", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    routes[CREATE] = () => scenario();
    render(<AttackScenarioPanel serviceId="svc" />);
    expect(
      (await screen.findByTestId("attack-scenario-add")).querySelector("legend")
        ?.textContent,
    ).toBe("Tools to add");
    fireEvent.click(screen.getByRole("button", { name: "Add a tool" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "XDR Suite" },
    });
    fireEvent.change(screen.getByLabelText("Vendor (optional)"), {
      target: { value: "Vendor X" },
    });
    expect(screen.getByLabelText("Category (optional)")).toBeTruthy();
    expect(screen.getByText("What it does:")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Prevent"));
    fireEvent.click(screen.getByLabelText("Detect"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByTestId("attack-scenario");
    expect(posts()).toEqual([
      {
        removed: [],
        added: [
          {
            name: "XDR Suite",
            vendor: "Vendor X",
            category: null,
            security_functions: ["detect", "prevent"],
          },
        ],
      },
    ]);
  });

  it("drops a tool to add with Remove this tool", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    render(<AttackScenarioPanel serviceId="svc" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a tool" }));
    expect(screen.getAllByLabelText("Name")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Remove this tool" }));
    expect(screen.queryAllByLabelText("Name")).toHaveLength(0);
  });

  it("names the gaps an added tool could fill (B9), plural and singular", async () => {
    await show({ affected_by_removal: 0, affected_by_addition_only: 2 });
    expect(
      screen.getByTestId("attack-scenario-affected-added").textContent,
    ).toBe(
      "2 techniques have a gap an added tool could fill, and will be re-assessed.",
    );
    expect(screen.queryByTestId("attack-scenario-affected")).toBeNull();
    expect(screen.getByTestId("attack-scenario-added-tools").textContent).toBe(
      "Tools to add: XDR Suite",
    );
  });

  it("splits the affected count between a removal (copy 6) and an addition (B9)", async () => {
    await show({
      removed: ["EDR Tool"],
      affected_codes: ["T1005", "T1008", "T1012"],
      affected_by_removal: 2,
      affected_by_addition_only: 1,
    });
    expect(screen.getByTestId("attack-scenario-affected").textContent).toBe(
      "2 techniques use these tools and will be re-assessed.",
    );
    expect(
      screen.getByTestId("attack-scenario-affected-added").textContent,
    ).toBe(
      "1 technique has a gap an added tool could fill, and will be re-assessed.",
    );
  });

  it("states B10, B14 and B11 beside the results when tools were added", async () => {
    await show({
      ...COMPLETED,
      higher_with_added: 2,
      differences: [
        {
          technique_code: "T1005",
          today: "gap",
          after: "partial",
          scored_higher: false,
          credited_added_tool: false,
          credited_tool_you_added: true,
        },
        {
          technique_code: "T1008",
          today: "covered",
          after: "partial",
          scored_higher: false,
          credited_added_tool: false,
          credited_tool_you_added: false,
        },
      ],
    });
    expect(
      screen.getByText(
        "Only the techniques these changes could affect were re-assessed. Every other technique is as the last confirmed assessment has it.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText(
        "Only the techniques these tools appear on were re-assessed. Every other technique is as the last confirmed assessment has it.",
      ),
    ).toBeNull();
    expect(
      screen.getByTestId("attack-scenario-added-in-place").textContent,
    ).toBe(
      "Tools you added count as in place. The AI judged what they cover from the name and functions you entered; they are not on the client's list.",
    );
    expect(screen.getByTestId("attack-scenario-higher-added").textContent).toBe(
      "2 techniques would score higher with the added tools.",
    );
    const marks = screen.getAllByTestId("attack-scenario-diff-you-added");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("Credited to a tool you added");
    expect(marks[0].closest("tr")?.textContent).toContain("T1005");
  });

  it("states B11 in the singular", async () => {
    await show({ ...COMPLETED, higher_with_added: 1 });
    expect(screen.getByTestId("attack-scenario-higher-added").textContent).toBe(
      "1 technique would score higher with the added tools.",
    );
  });

  it("states B14 only when tools were added", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    routes[CREATE] = () =>
      scenario({
        ...COMPLETED,
        removed: ["EDR Tool"],
        added: [],
        affected_by_removal: 2,
        affected_by_addition_only: 0,
      });
    render(<AttackScenarioPanel serviceId="svc" />);
    fireEvent.click(await screen.findByLabelText("EDR Tool"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByTestId("scenario-after");
    expect(screen.queryByTestId("attack-scenario-added-in-place")).toBeNull();
    expect(screen.queryByTestId("attack-scenario-higher-added")).toBeNull();
  });

  it("says why a suggestion crediting a client tool for an open function was set aside (B13)", async () => {
    await show({ ...COMPLETED, dropped: { tool_not_added: 2 } });
    expect(
      screen
        .getAllByTestId("attack-scenario-dropped")
        .map((p) => p.textContent),
    ).toEqual([
      "2 AI suggestions were set aside because they credited one of the client's tools where only an added tool was asked about.",
    ]);
  });

  it("says why a suggestion crediting an added tool beyond its declared functions was set aside", async () => {
    await show({ ...COMPLETED, dropped: { function_not_declared: 2 } });
    expect(
      screen
        .getAllByTestId("attack-scenario-dropped")
        .map((p) => p.textContent),
    ).toEqual([
      "2 AI suggestions were set aside because they credited an added tool with something you did not choose for it.",
    ]);
  });

  it("states the undeclared-function line in the singular", async () => {
    await show({ ...COMPLETED, dropped: { function_not_declared: 1 } });
    expect(
      screen
        .getAllByTestId("attack-scenario-dropped")
        .map((p) => p.textContent),
    ).toEqual([
      "1 AI suggestion was set aside because it credited an added tool with something you did not choose for it.",
    ]);
  });

  it("states B13 in the singular", async () => {
    await show({ ...COMPLETED, dropped: { tool_not_added: 1 } });
    expect(
      screen
        .getAllByTestId("attack-scenario-dropped")
        .map((p) => p.textContent),
    ).toEqual([
      "1 AI suggestion was set aside because it credited one of the client's tools where only an added tool was asked about.",
    ]);
  });

  it("says nothing about added tools' rises when there are none (B11 above 0 only)", async () => {
    await show({ ...COMPLETED, higher_with_added: 0 });
    expect(screen.getByTestId("attack-scenario-added-in-place")).toBeTruthy();
    expect(screen.queryByTestId("attack-scenario-higher-added")).toBeNull();
  });

  it("an addition-only what-if's unanswered techniques show the assessment unchanged", async () => {
    await show({ ...COMPLETED, not_reassessed: ["T1005", "T1008"] });
    expect(
      screen.getByTestId("attack-scenario-not-reassessed").textContent,
    ).toBe(
      "2 techniques could not be re-assessed because the AI did not answer for them. They show the last confirmed assessment unchanged.",
    );
  });

  it("lists a what-if that adds tools with both halves labelled", async () => {
    routes[LIST] = () => ({
      base: BASE,
      scenarios: [
        {
          id: "s9",
          state: "draft",
          removed: ["EDR Tool"],
          added: ["XDR Suite"],
          affected_count: 3,
          base_version: 3,
          created_at: "2026-10-03T06:00:00Z",
        },
        {
          id: "s8",
          state: "draft",
          removed: [],
          added: ["XDR Suite"],
          affected_count: 2,
          base_version: 3,
          created_at: "2026-10-03T05:00:00Z",
        },
      ],
    });
    render(<AttackScenarioPanel serviceId="svc" />);
    const rows = (
      await screen.findByTestId("attack-scenario-list")
    ).querySelectorAll("li");
    expect(
      [...rows].map((li) => li.querySelector("span")?.textContent),
    ).toEqual([
      "Tools to remove: EDR Tool; Tools to add: XDR Suite (compared with version 3)",
      "Tools to add: XDR Suite (compared with version 3)",
    ]);
  });

  it("runs a stale what-if again with the same tools to add", async () => {
    await show({ stale: true });
    routes[CREATE] = () => scenario({ id: "s2" });
    fireEvent.click(screen.getByRole("button", { name: "Run it again" }));
    await waitFor(() => expect(posts()).toHaveLength(2));
    expect(posts()[1]).toEqual({ removed: [], added: [XDR] });
  });
});
