import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AttackAiInputsPanel } from "./AttackAiInputsPanel";

import type { AttackAiInputs } from "@/lib/attack/types";

/**
 * This panel exists because the workspace reported a single number, after the
 * run. A run with ZERO capabilities then wrote 607 fabricated gaps that read
 * exactly like a real assessment. So the assertions that matter are: the count
 * is visible before the run, zero is LOUD, and nothing about the inputs is
 * quietly omitted.
 */

vi.mock("@/lib/attack/client", () => ({ fetchAttackAiInputs: vi.fn() }));

const { fetchAttackAiInputs } = await import("@/lib/attack/client");
const mockFetch = vi.mocked(fetchAttackAiInputs);

function inputs(over: Partial<AttackAiInputs> = {}): AttackAiInputs {
  return {
    service_id: "svc-1",
    tools_sent: 2,
    items_in_scope: 2,
    duplicate_names: 0,
    awaiting_signoff_count: 0,
    items_without_source_document: 0,
    documents: [],
    lists: [
      {
        capability_list_id: "l1",
        tech_debt_service_id: "td1",
        tech_debt_service_title: "Acme Tech Debt",
        version: 1,
        status: "approved",
        is_latest_for_service: true,
        item_count: 2,
      },
    ],
    items: [
      {
        name: "CrowdStrike Falcon",
        vendor: "CrowdStrike",
        category: "EDR",
        security_functions: ["detect", "respond"],
        awaiting_signoff: false,
        source_document_id: "a1",
        capability_list_id: "l1",
        list_label: "Acme Tech Debt v1",
        list_is_superseded: false,
      },
      {
        name: "Splunk",
        vendor: null,
        category: null,
        security_functions: [],
        awaiting_signoff: false,
        source_document_id: null,
        capability_list_id: "l1",
        list_label: "Acme Tech Debt v1",
        list_is_superseded: false,
      },
    ],
    ...over,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("AttackAiInputsPanel", () => {
  it("states the count without the admin having to expand anything", async () => {
    mockFetch.mockResolvedValue(inputs());
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    expect(
      await screen.findByText(
        /Mapping against 2 security capabilities from 1 Tech Debt list\./,
      ),
    ).toBeInTheDocument();
  });

  it("keeps the line-by-line table behind a disclosure", async () => {
    mockFetch.mockResolvedValue(inputs());
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    await screen.findByTestId("attack-ai-inputs");
    // Present in the DOM but inside <details>, so the page stays short.
    const details = screen.getByTestId("attack-ai-inputs-table");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("Show all 2 capabilities")).toBeInTheDocument();
  });

  it("shows each capability with the fields the model now receives", async () => {
    mockFetch.mockResolvedValue(inputs());
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    await screen.findByTestId("attack-ai-inputs");
    expect(
      screen.getByRole("rowheader", { name: /CrowdStrike Falcon/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("detect, respond")).toBeInTheDocument();
  });

  it("makes zero capabilities loud, not a quiet count", async () => {
    // The N-033 signal. A small grey "0" is what let 607 fabricated gaps ship.
    mockFetch.mockResolvedValue(
      inputs({ tools_sent: 0, items_in_scope: 0, items: [], lists: [] }),
    );
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    expect(
      await screen.findByText(/No security capabilities will be sent/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/would report every technique as a gap/),
    ).toBeInTheDocument();
  });

  it("offers the source document for download", async () => {
    mockFetch.mockResolvedValue(
      inputs({
        documents: [
          {
            id: "a1",
            title: "Enterprise_Inventory.xlsx",
            mime_type: "application/vnd.ms-excel",
            size_bytes: 20480,
            uploaded_at: "2026-08-01T00:00:00Z",
            item_count: 2,
          },
        ],
      }),
    );
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    expect(
      await screen.findByText("Enterprise_Inventory.xlsx"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "href",
      "/api/proxy/artifacts/a1/download",
    );
  });

  it("says in words that a superseded list still feeds the mapping", async () => {
    // It surprises people, and inferring it from a version number is not
    // disclosure.
    mockFetch.mockResolvedValue(
      inputs({
        lists: [
          {
            capability_list_id: "l1",
            tech_debt_service_id: "td1",
            tech_debt_service_title: "Acme Tech Debt",
            version: 1,
            status: "approved",
            is_latest_for_service: false,
            item_count: 2,
          },
        ],
      }),
    );
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    expect(
      await screen.findByText(/Includes a superseded list version/),
    ).toBeInTheDocument();
    expect(screen.getByText(/still offered to the model/)).toBeInTheDocument();
  });

  it("flags rows awaiting security sign-off", async () => {
    mockFetch.mockResolvedValue(inputs({ awaiting_signoff_count: 1 }));
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    expect(
      await screen.findByText("1 awaiting security sign-off"),
    ).toBeInTheDocument();
  });

  it("reports rows with no traceable source rather than omitting them", async () => {
    mockFetch.mockResolvedValue(inputs({ items_without_source_document: 1 }));
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    expect(
      await screen.findByText("1 with no source document"),
    ).toBeInTheDocument();
  });

  it("fails loudly — a vanished panel would read as 'no capabilities'", async () => {
    mockFetch.mockRejectedValue(new Error("Upstream exploded."));
    render(<AttackAiInputsPanel serviceId="svc-1" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Upstream exploded.");
  });
});
