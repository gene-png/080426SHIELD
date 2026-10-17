import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as csfClient from "@/lib/csf/client";
import type { CsfAssessment, CsfCatalog } from "@/lib/csf/types";
import type { SectionKey } from "@/components/service-shell/SectionBar";

import { CsfWorkspace } from "./CsfWorkspace";

// #1378: which blocks each section of the client frame shows. Children are
// stubbed to a marker so the test reads WHERE a block is rendered, and the
// expected placement below is written from the issue's component map, not from
// `CSF_BLOCK_SECTIONS`.
vi.mock("@/lib/csf/client", () => ({
  CsfProxyError: class extends Error {},
  fetchCatalog: vi.fn(),
  fetchInterviewQuestionnaire: vi.fn(),
  fetchLatestAssessment: vi.fn(),
  fetchLatestDeliverable: vi.fn(),
  fetchScore: vi.fn(),
  fetchGapAnalysis: vi.fn(),
  createAssessment: vi.fn(),
  approveAssessment: vi.fn(),
  discardAssessment: vi.fn(),
  startRevision: vi.fn(),
  patchAnswer: vi.fn(),
}));
vi.mock("./CsfScoreCard", () => ({
  CsfScoreCard: () => <div data-testid="m-score" />,
}));
vi.mock("./CsfPlaybookPanel", () => ({
  CsfPlaybookPanel: ({ section }: { section?: string }) => (
    <div data-testid="m-panel" data-panel-section={section} />
  ),
}));
vi.mock("./CsfGapList", () => ({
  CsfGapList: () => <div data-testid="m-gaplist" />,
}));
vi.mock("./CsfDeliverableCard", () => ({
  CsfDeliverableCard: () => <div data-testid="m-deliverable" />,
}));
vi.mock("./CsfQuestionnaire", () => ({
  CsfQuestionnaire: () => <div data-testid="m-questionnaire" />,
}));
vi.mock("@/components/messages/MessageThread", () => ({
  MessageThread: () => <div data-testid="m-messages" />,
}));
vi.mock("@/components/admin/StaleDocsNudge", () => ({
  StaleDocsNudge: () => <div data-testid="m-stale" />,
}));

function assessment(status: string): CsfAssessment {
  return {
    id: "assess-1",
    status,
    version: 1,
    answers: [],
    client_target_tier: 3,
    documents_stale: false,
    ai_source: {
      state: "none",
      sentence: "No AI suggestions were used in this assessment.",
      live_runs: 0,
      fixture_runs: 0,
    },
  } as unknown as CsfAssessment;
}

async function mount(section: SectionKey, status = "draft") {
  vi.mocked(csfClient.fetchCatalog).mockResolvedValue({} as CsfCatalog);
  vi.mocked(csfClient.fetchInterviewQuestionnaire).mockResolvedValue(null);
  vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(
    assessment(status),
  );
  vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
  vi.mocked(csfClient.fetchScore).mockResolvedValue(null as never);
  vi.mocked(csfClient.fetchGapAnalysis).mockResolvedValue(null as never);
  render(
    <CsfWorkspace
      serviceId="svc-1"
      serviceTitle="Atlas CSF"
      section={section}
    />,
  );
  await screen.findByText(/(Draft|Approved|Released) v1/);
}

const MARKERS = [
  "m-score",
  "m-panel",
  "m-gaplist",
  "m-deliverable",
  "m-questionnaire",
  "m-messages",
  "m-stale",
] as const;

function shown(): string[] {
  return MARKERS.filter((m) => screen.queryByTestId(m) !== null);
}

describe("CsfWorkspace in a section (#1378)", () => {
  it.each([
    ["overview", ["m-score", "m-messages"]],
    ["ai-draft", ["m-panel", "m-questionnaire"]],
    ["review", ["m-panel"]],
    ["analysis", ["m-panel", "m-gaplist"]],
    ["generate", ["m-deliverable", "m-stale"]],
    ["quality-check", []],
    ["approve-and-release", []],
  ] as const)("%s shows only its own blocks", async (section, expected) => {
    await mount(section);
    expect(shown().sort()).toEqual([...expected].sort());
  });

  it("tells each part of the playbook panel which section it is in", async () => {
    await mount("review");
    expect(screen.getByTestId("m-panel")).toHaveAttribute(
      "data-panel-section",
      "review",
    );
  });

  it("puts Approve in Review only", async () => {
    await mount("review");
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it.each(["overview", "ai-draft", "analysis", "generate"] as const)(
    "has no Approve button in %s",
    async (section) => {
      await mount(section);
      expect(
        screen.queryByRole("button", { name: "Approve" }),
      ).not.toBeInTheDocument();
    },
  );

  it("puts Discard draft in Overview only", async () => {
    await mount("overview");
    expect(
      screen.getByRole("button", { name: "Discard draft" }),
    ).toBeInTheDocument();
  });

  it("does not put Discard draft in Review", async () => {
    await mount("review");
    expect(
      screen.queryByRole("button", { name: "Discard draft" }),
    ).not.toBeInTheDocument();
  });

  it("puts Start a revision in Approve and release only", async () => {
    await mount("approve-and-release", "released");
    expect(
      screen.getByRole("button", { name: /Start a revision/ }),
    ).toBeInTheDocument();
  });

  it("does not put Start a revision in Overview", async () => {
    await mount("overview", "released");
    expect(
      screen.queryByRole("button", { name: /Start a revision/ }),
    ).not.toBeInTheDocument();
  });

  it("has the section's title once, and not the old page title", async () => {
    await mount("review");
    expect(screen.getByRole("heading", { name: "Review" })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Atlas CSF" }),
    ).not.toBeInTheDocument();
  });
});

describe("CsfWorkspace with no section", () => {
  it("keeps the whole page, as before", async () => {
    vi.mocked(csfClient.fetchCatalog).mockResolvedValue({} as CsfCatalog);
    vi.mocked(csfClient.fetchInterviewQuestionnaire).mockResolvedValue(null);
    vi.mocked(csfClient.fetchLatestAssessment).mockResolvedValue(
      assessment("draft"),
    );
    vi.mocked(csfClient.fetchLatestDeliverable).mockResolvedValue(null);
    vi.mocked(csfClient.fetchScore).mockResolvedValue(null as never);
    vi.mocked(csfClient.fetchGapAnalysis).mockResolvedValue(null as never);
    render(<CsfWorkspace serviceId="svc-1" serviceTitle="Atlas CSF" />);
    await screen.findByText("Draft v1");
    expect(shown().sort()).toEqual([...MARKERS].sort());
    expect(
      screen.getByRole("heading", { name: "Atlas CSF" }),
    ).toBeInTheDocument();
  });
});
