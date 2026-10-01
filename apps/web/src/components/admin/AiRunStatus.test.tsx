import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AiRun } from "@/lib/aiRuns/types";

import { AiRunStatus, clockTime } from "./AiRunStatus";

function run(over: Partial<AiRun<unknown>> = {}): AiRun<unknown> {
  return {
    id: "run-1",
    service_id: "svc-1",
    purpose: "mitre_map",
    status: "running",
    serves: "live",
    started_at: "2026-10-01T12:00:00Z",
    deadline_at: "2026-10-01T12:45:00Z",
    finished_at: null,
    batches_total: null,
    batches_failed: null,
    applied_count: null,
    result: null,
    error_reason: null,
    error_message: null,
    charged_likely: null,
    ...over,
  };
}

const READY = {
  phase: "ready" as const,
  loadError: null,
  running: null,
  latest: null,
  checkFailed: false,
};

describe("AiRunStatus (#645)", () => {
  it("shows the lock and when it ends at the latest while a run is in progress", () => {
    render(<AiRunStatus run={{ ...READY, running: run() }} />);
    const el = screen.getByTestId("ai-run-running");
    expect(el).toHaveTextContent(/AI run in progress/);
    expect(el).toHaveTextContent(/Editing this assessment is locked/);
    expect(el).toHaveTextContent(clockTime("2026-10-01T12:45:00Z"));
    expect(screen.queryByTestId("ai-run-check-failed")).toBeNull();
  });

  it("says it could not check, and never that the run failed", () => {
    render(
      <AiRunStatus run={{ ...READY, running: run(), checkFailed: true }} />,
    );
    expect(screen.getByTestId("ai-run-running")).toBeInTheDocument();
    expect(screen.getByTestId("ai-run-check-failed")).toHaveTextContent(
      /Could not check on the run just now, so it may still be running/,
    );
    expect(screen.queryByTestId("ai-run-failed")).toBeNull();
    expect(screen.queryByText(/failed/i)).toBeNull();
  });

  it.each([
    [true, /provider has probably charged/],
    [false, /made no live AI call/],
    [null, /Whether it made a billable AI call is not known/],
  ])(
    "states a failed run's reason and charged_likely=%s in words",
    (charged, words) => {
      render(
        <AiRunStatus
          run={{
            ...READY,
            latest: run({
              status: "failed",
              error_reason: "ai_call_failed",
              error_message: "The AI provider closed the connection.",
              charged_likely: charged,
            }),
          }}
        />,
      );
      const el = screen.getByTestId("ai-run-failed");
      expect(el).toHaveTextContent(/The last AI run failed/);
      expect(el).toHaveTextContent(/closed the connection/);
      expect(el).toHaveTextContent(words);
    },
  );

  it("says so when it could not read whether a run is in progress", () => {
    render(
      <AiRunStatus run={{ ...READY, phase: "error", loadError: "down" }} />,
    );
    expect(screen.getByTestId("ai-run-load-failed")).toHaveTextContent(
      /Could not check whether an AI run is in progress/,
    );
  });

  it("renders nothing for a completed run: its disclosures are the service's", () => {
    const { container } = render(
      <AiRunStatus
        run={{ ...READY, latest: run({ status: "completed", result: {} }) }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
