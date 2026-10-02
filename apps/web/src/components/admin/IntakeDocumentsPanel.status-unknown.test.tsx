import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { listArtifacts } from "@/lib/intake/artifacts";

import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";

/**
 * #645: the Tech Debt surface of the Run-AI guard. The REAL RunAiGuard, with
 * its AI status set here: an unreadable status disables "Extract from this",
 * and a later successful read enables it again.
 */
vi.mock("@/lib/intake/artifacts", () => ({ listArtifacts: vi.fn() }));
const aiStatus = vi.hoisted(() => {
  const ok = {
    ready: true,
    serves: "live",
    mode: "live",
    provider: "anthropic",
    model: "m",
    detail: "",
    can_configure: true,
    key_source: "database",
  };
  return { ok, current: { status: null as unknown, phase: "error" as string } };
});
vi.mock("@/lib/admin/aiStatus", () => ({
  useAiStatus: () => ({
    status: aiStatus.current.status,
    phase: aiStatus.current.phase,
    settled: async () => aiStatus.current.status,
    refresh: () => undefined,
  }),
  hasAcknowledgedOffline: () => false,
  acknowledgeOffline: () => undefined,
}));

const DOCS = {
  items: [
    {
      id: "doc-a",
      title: "a.csv",
      mime_type: "text/csv",
      size_bytes: 1024,
      uploaded_at: "2026-09-26T00:00:00Z",
      origin: "client_upload",
    },
  ],
};

describe("IntakeDocumentsPanel, an unreadable AI status (#645)", () => {
  it("disables extraction while the status is unknown, and enables it after a later read succeeds", async () => {
    vi.mocked(listArtifacts).mockResolvedValue(DOCS as never);
    const el = (
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />
    );
    const { rerender } = render(el);
    const button = await screen.findByRole("button", {
      name: "Extract from this",
    });
    expect(button).toBeDisabled();
    expect(screen.getByTestId("run-ai-status-unknown")).toHaveTextContent(
      /Reload the page/,
    );

    aiStatus.current = { status: aiStatus.ok, phase: "loaded" };
    rerender(
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Extract from this" }),
      ).toBeEnabled(),
    );
    expect(screen.queryByTestId("run-ai-status-unknown")).toBeNull();
  });
});
