import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listArtifacts } from "@/lib/intake/artifacts";

import { IntakeDocumentsPanel } from "./IntakeDocumentsPanel";

vi.mock("@/lib/intake/artifacts", () => ({ listArtifacts: vi.fn() }));

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
    {
      id: "doc-b",
      title: "b.csv",
      mime_type: "text/csv",
      size_bytes: 2048,
      uploaded_at: "2026-09-26T00:00:00Z",
      origin: "client_upload",
    },
  ],
};

vi.mock("@/components/admin/RunAiGuard", () => ({
  RunAiGuard: ({
    children,
  }: {
    children: (p: { onClick: () => void }) => React.ReactNode;
  }) => children({ onClick: () => undefined }),
}));

async function rowFor(title: string): Promise<HTMLElement> {
  const name = await screen.findByText(title);
  const row = name.closest("li");
  if (!row) throw new Error(`no row for ${title}`);
  return row;
}

describe("IntakeDocumentsPanel open-draft source (#644)", () => {
  beforeEach(() => {
    vi.mocked(listArtifacts).mockResolvedValue(DOCS as never);
  });

  it("marks the document the open draft came from, and only that one", async () => {
    render(
      <IntakeDocumentsPanel
        onExtract={() => undefined}
        extracting={false}
        draftSourceId="doc-a"
      />,
    );
    expect(
      within(await rowFor("a.csv")).getByText("Current draft"),
    ).toBeVisible();
    expect(
      within(await rowFor("b.csv")).queryByText("Current draft"),
    ).toBeNull();
    expect(screen.getByTestId("draft-source-hint")).toHaveTextContent(
      'The open draft was extracted from a.csv. To extract from another document, use "Discard draft" in step 2 first.',
    );
  });

  it("marks nothing when no draft source is known", async () => {
    render(
      <IntakeDocumentsPanel onExtract={() => undefined} extracting={false} />,
    );
    await rowFor("a.csv");
    expect(screen.queryByText("Current draft")).toBeNull();
    expect(screen.queryByTestId("draft-source-hint")).toBeNull();
  });
});
