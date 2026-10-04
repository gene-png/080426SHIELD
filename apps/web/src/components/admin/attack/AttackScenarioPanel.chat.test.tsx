import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttackScenarioPanel } from "./AttackScenarioPanel";

/**
 * #802 slice C: the chat box. Copy C1-C9 approved by the advisor at 18:32Z;
 * every sentence here is asserted byte for byte.
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
const PARSE = "POST /api/proxy/attack/services/svc/scenarios/parse";
const CREATE = "POST /api/proxy/attack/services/svc/scenarios";

async function describeChange(
  text: string,
  answer: Record<string, unknown>,
): Promise<void> {
  routes[LIST] = () => ({ base: BASE, scenarios: [] });
  routes[PARSE] = () => answer;
  render(<AttackScenarioPanel serviceId="svc" />);
  fireEvent.change(await screen.findByLabelText("Describe the change"), {
    target: { value: text },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Fill in the change list" }),
  );
}

describe("AttackScenarioPanel, the chat box (slice C)", () => {
  it("shows C1, C2 and C3", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    render(<AttackScenarioPanel serviceId="svc" />);
    expect(await screen.findByLabelText("Describe the change")).toBeTruthy();
    expect(
      screen.getByText('For example "retire X and Y" or "swap X for Z".'),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Fill in the change list" }),
    ).toBeTruthy();
  });

  it("sends the text, fills in the picker, and says so (C4)", async () => {
    await describeChange("swap EDR Tool for XDR Suite", {
      removed: ["EDR Tool"],
      added: ["XDR Suite"],
      not_understood: [],
    });
    expect(
      (await screen.findByTestId("attack-scenario-chat-filled")).textContent,
    ).toBe(
      "The change list below was filled in from your description. Check it before you continue.",
    );
    const parse = calls.find((c) => c.url.endsWith("/scenarios/parse"));
    expect(JSON.parse(String(parse?.init?.body))).toEqual({
      text: "swap EDR Tool for XDR Suite",
    });
    expect(
      (screen.getByLabelText("EDR Tool") as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByLabelText("SIEM Tool") as HTMLInputElement).checked,
    ).toBe(false);
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe(
      "XDR Suite",
    );
  });

  it("asks what an added tool does until it is chosen (C9)", async () => {
    await describeChange("add XDR Suite", {
      removed: [],
      added: ["XDR Suite"],
      not_understood: [],
    });
    expect(
      (await screen.findByTestId("attack-scenario-chat-functions")).textContent,
    ).toBe("Choose what XDR Suite does before you continue.");
    fireEvent.click(screen.getByLabelText("Detect"));
    expect(screen.queryByTestId("attack-scenario-chat-functions")).toBeNull();
  });

  it("quotes back each clause not understood, in the api's words (C5)", async () => {
    await describeChange("remove EDR, polish it", {
      removed: [],
      added: [],
      not_understood: [
        {
          text: "remove EDR",
          reason: "unknown_tool",
          message:
            'Not understood: "remove EDR". Pick the tool from the list instead.',
        },
      ],
    });
    expect(
      (await screen.findAllByTestId("attack-scenario-chat-not-understood")).map(
        (p) => p.textContent,
      ),
    ).toEqual([
      'Not understood: "remove EDR". Pick the tool from the list instead.',
    ]);
  });

  it("says nothing matched when nothing did (C6), and not C4", async () => {
    await describeChange("polish it", {
      removed: [],
      added: [],
      not_understood: [],
    });
    expect(
      (await screen.findByTestId("attack-scenario-chat-nothing")).textContent,
    ).toBe(
      "Nothing in your description matched a change. Pick the tools from the list instead.",
    );
    expect(screen.queryByTestId("attack-scenario-chat-filled")).toBeNull();
  });

  it("shows the api's typed refusal (C7)", async () => {
    await describeChange("", {
      __status: 422,
      error: {
        reason: "scenario_chat_empty",
        message: "Describe the change first.",
      },
    });
    expect(
      (await screen.findByTestId("attack-scenario-chat-error")).textContent,
    ).toBe("Describe the change first.");
  });

  it("says to try again when the parse fails with no sentence of its own", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    routes[PARSE] = () => {
      throw new TypeError("Failed to fetch");
    };
    render(<AttackScenarioPanel serviceId="svc" />);
    fireEvent.change(await screen.findByLabelText("Describe the change"), {
      target: { value: "retire EDR Tool" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Fill in the change list" }),
    );
    // Approved by the advisor at 19:18Z, byte for byte.
    expect(
      (await screen.findByTestId("attack-scenario-chat-error")).textContent,
    ).toBe("The description could not be checked. Try again.");
  });

  it("creates and runs nothing; Continue sends what the admin left after editing", async () => {
    await describeChange("retire EDR Tool and SIEM Tool", {
      removed: ["EDR Tool", "SIEM Tool"],
      added: [],
      not_understood: [],
    });
    await screen.findByTestId("attack-scenario-chat-filled");
    expect(calls.map((c) => `${c.init?.method ?? "GET"} ${c.url}`)).toEqual([
      LIST,
      PARSE,
    ]);
    fireEvent.click(screen.getByLabelText("SIEM Tool")); // the admin unticks one
    routes[CREATE] = () => ({ __status: 422, error: { message: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.url.endsWith("/svc/scenarios") && c.init?.method === "POST",
        ),
      ).toBe(true),
    );
    const create = calls.find(
      (c) => c.url.endsWith("/svc/scenarios") && c.init?.method === "POST",
    );
    expect(JSON.parse(String(create?.init?.body))).toEqual({
      removed: ["EDR Tool"],
    });
  });

  // --- #824 review: B2 (merge) and B3 (late results) ---------------------------

  async function withPriorChoices(): Promise<void> {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    render(<AttackScenarioPanel serviceId="svc" />);
    fireEvent.click(await screen.findByLabelText("SIEM Tool"));
    fireEvent.click(screen.getByRole("button", { name: "Add a tool" }));
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Typed Tool" },
    });
  }

  function fillWith(answer: unknown, text = "x"): void {
    routes[PARSE] = () => answer;
    fireEvent.change(screen.getByLabelText("Describe the change"), {
      target: { value: text },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Fill in the change list" }),
    );
  }

  it("an empty proposal keeps what the admin ticked and typed", async () => {
    await withPriorChoices();
    fillWith({ removed: [], added: [], not_understood: [] });
    await screen.findByTestId("attack-scenario-chat-nothing");
    expect(
      (screen.getByLabelText("SIEM Tool") as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      screen
        .getAllByLabelText("Name")
        .map((i) => (i as HTMLInputElement).value),
    ).toEqual(["Typed Tool"]);
  });

  it("a proposal MERGES into what the admin ticked and typed", async () => {
    await withPriorChoices();
    fillWith({
      removed: ["EDR Tool"],
      added: ["XDR Suite", "typed tool"],
      not_understood: [],
    });
    await screen.findByTestId("attack-scenario-chat-filled");
    expect(
      (screen.getByLabelText("SIEM Tool") as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByLabelText("EDR Tool") as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      screen
        .getAllByLabelText("Name")
        .map((i) => (i as HTMLInputElement).value),
    ).toEqual(["Typed Tool", "XDR Suite"]);
  });

  it("holds the picker still while a parse is in flight", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    render(<AttackScenarioPanel serviceId="svc" />);
    await screen.findByLabelText("Describe the change");
    let release: (v: unknown) => void = () => undefined;
    fillWith(new Promise((r) => (release = r)));
    await waitFor(() =>
      expect(screen.getByLabelText("EDR Tool").matches(":disabled")).toBe(true),
    );
    expect(
      (screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    release({ removed: [], added: [], not_understood: [] });
    await waitFor(() =>
      expect(screen.getByLabelText("EDR Tool").matches(":disabled")).toBe(
        false,
      ),
    );
  });

  it("a service change empties the picker, and a late parse for the old one lands nowhere", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    routes["GET /api/proxy/attack/services/svc2/scenarios"] = () => ({
      base: BASE,
      scenarios: [],
    });
    const { rerender } = render(<AttackScenarioPanel serviceId="svc" />);
    fireEvent.click(await screen.findByLabelText("SIEM Tool"));
    let release: (v: unknown) => void = () => undefined;
    fillWith(new Promise((r) => (release = r)));
    rerender(<AttackScenarioPanel serviceId="svc2" />);
    await waitFor(() =>
      expect(
        (screen.getByLabelText("SIEM Tool") as HTMLInputElement).checked,
      ).toBe(false),
    );
    release({ removed: ["EDR Tool"], added: [], not_understood: [] });
    await new Promise((r) => setTimeout(r, 30));
    expect(
      (screen.getByLabelText("EDR Tool") as HTMLInputElement).checked,
    ).toBe(false);
    expect(screen.getByLabelText("EDR Tool").matches(":disabled")).toBe(false);
    // Nor does the new service's chat box claim it filled anything in.
    expect(screen.queryByTestId("attack-scenario-chat-filled")).toBeNull();
  });

  it("a parse orphaned by a service change is not applied on coming back", async () => {
    routes[LIST] = () => ({ base: BASE, scenarios: [] });
    routes["GET /api/proxy/attack/services/svc2/scenarios"] = () => ({
      base: BASE,
      scenarios: [],
    });
    const { rerender } = render(<AttackScenarioPanel serviceId="svc" />);
    await screen.findByLabelText("EDR Tool");
    let release: (v: unknown) => void = () => undefined;
    fillWith(new Promise((r) => (release = r)));
    rerender(<AttackScenarioPanel serviceId="svc2" />);
    await screen.findByLabelText("EDR Tool");
    release({
      removed: ["EDR Tool"],
      added: ["XDR Suite"],
      not_understood: [],
    });
    await new Promise((r) => setTimeout(r, 30));
    rerender(<AttackScenarioPanel serviceId="svc" />);
    await screen.findByLabelText("EDR Tool");
    expect(
      (screen.getByLabelText("EDR Tool") as HTMLInputElement).checked,
    ).toBe(false);
    expect(screen.queryByDisplayValue("XDR Suite")).toBeNull();
    expect(screen.queryByTestId("attack-scenario-chat-filled")).toBeNull();
  });
});

describe("AttackScenarioPanel, the chat box's AI reading (#802)", () => {
  const STATUS = "GET /api/proxy/admin/ai-status";

  function aiStatus(ready: boolean): Record<string, unknown> {
    return {
      mode: ready ? "live" : "fixture",
      provider: "provider",
      model: "m",
      ready,
      detail: "",
      can_configure: true,
      key_source: ready ? "database" : "none",
    };
  }

  it.each([
    [true, "live"],
    [false, "offline"],
  ])(
    "acknowledges live only while the AI is ready (ready=%s sends %s)",
    async (ready, serves) => {
      routes[STATUS] = () => aiStatus(ready);
      await describeChange("get rid of the edr thing", {
        removed: [],
        added: [],
        not_understood: [],
      });
      await screen.findByTestId("attack-scenario-chat-nothing");
      const parse = calls.find((c) => c.url.endsWith("/scenarios/parse"));
      expect(JSON.parse(String(parse?.init?.body))).toEqual({
        text: "get rid of the edr thing",
        serves,
      });
    },
  );

  it("sends offline when the AI status cannot be read", async () => {
    routes[STATUS] = () => ({ __status: 500, error: { message: "x" } });
    await describeChange("get rid of the edr thing", {
      removed: [],
      added: [],
      not_understood: [],
    });
    await screen.findByTestId("attack-scenario-chat-nothing");
    const parse = calls.find((c) => c.url.endsWith("/scenarios/parse"));
    expect(JSON.parse(String(parse?.init?.body)).serves).toBe("offline");
  });

  it("says the AI filled the list in (N1) when the AI read the text", async () => {
    routes[STATUS] = () => aiStatus(true);
    await describeChange("get rid of the edr thing", {
      removed: ["EDR Tool"],
      added: [],
      not_understood: [],
      source: "ai",
      note: null,
    });
    expect(
      (await screen.findByTestId("attack-scenario-chat-filled")).textContent,
    ).toBe(
      "The change list below was filled in by the AI from your description. Check it before you continue.",
    );
    expect(screen.queryByTestId("attack-scenario-chat-note")).toBeNull();
  });

  it("shows N2 when the AI could not be used, beside the matcher's reading", async () => {
    routes[STATUS] = () => aiStatus(true);
    const n2 =
      "The AI could not read your description just now, so only the tools named exactly as listed were filled in.";
    await describeChange("retire EDR Tool and the other thing", {
      removed: ["EDR Tool"],
      added: [],
      not_understood: [],
      source: "matcher",
      note: n2,
    });
    expect(
      (await screen.findByTestId("attack-scenario-chat-note")).textContent,
    ).toBe(n2);
    expect(screen.getByTestId("attack-scenario-chat-filled").textContent).toBe(
      "The change list below was filled in from your description. Check it before you continue.",
    );
  });
});
