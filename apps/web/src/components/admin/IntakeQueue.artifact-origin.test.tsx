import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntakeQueue } from "./IntakeQueue";

import type {
  AdminArtifactRow,
  AdminServiceRequestRow,
} from "@/lib/admin/types";
import type { useServiceStages as useServiceStagesType } from "@/lib/stages/client";

/**
 * #1054 (IN-2): the org page's "Uploaded documents" list held every Artifact
 * row of the tenant, and a released deliverable's PDF/XLSX/DOCX files are
 * Artifact rows too -- twelve generated reports listed as the client's
 * uploads. The page now splits on the STORED `origin`, never on a filename.
 *
 * The readiness checklist read the same list, so "Supporting documents
 * uploaded" ticked for a client who had uploaded nothing once any report had
 * been exported. That is asserted here too.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/admin/client", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  fetchIntakeQueue: vi.fn(),
  fulfillServiceRequest: vi.fn(),
}));
vi.mock("@/lib/stages/client", () => ({
  useServiceStages: () =>
    ({
      phase: "ready",
      stages: null,
    }) satisfies ReturnType<typeof useServiceStagesType>,
}));

const { fetchIntakeQueue } = await import("@/lib/admin/client");
const mockFetch = vi.mocked(fetchIntakeQueue);

function artifact(
  id: string,
  title: string,
  origin: AdminArtifactRow["origin"],
): AdminArtifactRow {
  return {
    id,
    title,
    mime_type: "application/pdf",
    size_bytes: 2048,
    uploaded_by: "u1",
    uploaded_at: "2026-10-01T12:00:00Z",
    origin,
  };
}

const request = {
  id: "r1",
  service_type: "nist_csf",
  requested_at: "2026-10-01T12:00:00Z",
  requested_by: {
    id: "u1",
    email: "a@example.com",
    display_name: "A",
    role: "client",
  },
  notes: null,
  deadline: null,
  csf_target_tier: null,
  csf_profile: null,
  zt_target_stage: null,
  fulfilled_service_id: null,
  declined_at: null,
  declined_reason: null,
} as unknown as AdminServiceRequestRow;

function serve(artifacts: AdminArtifactRow[]): void {
  mockFetch.mockResolvedValue({
    client: null,
    intake_completed_at: null,
    service_requests: [request],
    artifacts,
    total_users: 1,
  });
}

function section(headingPattern: RegExp): HTMLElement {
  const heading = screen.getByRole("heading", { name: headingPattern });
  const el = heading.closest("section");
  if (!el) throw new Error(`no section around ${headingPattern}`);
  return el;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("IntakeQueue — client uploads vs generated reports (#1054)", () => {
  it("lists each artifact under the section its stored origin names", async () => {
    serve([
      artifact("a1", "network-inventory.csv", "client_upload"),
      artifact("a2", "NIST-CSF-Report-v1.pdf", "consultant_approved"),
      artifact("a3", "NIST-CSF-Report-v1.xlsx", "consultant_approved"),
    ]);
    render(<IntakeQueue clientId="00000000-0000-4000-8000-000000000001" />);
    await screen.findByRole("heading", { name: /^Uploaded documents \(1\)$/ });

    const uploads = section(/^Uploaded documents \(1\)$/);
    expect(
      within(uploads).getByText("network-inventory.csv"),
    ).toBeInTheDocument();
    expect(
      within(uploads).queryByText("NIST-CSF-Report-v1.pdf"),
    ).not.toBeInTheDocument();

    const reports = section(/^Generated reports \(2\)$/);
    expect(
      within(reports).getByText("NIST-CSF-Report-v1.pdf"),
    ).toBeInTheDocument();
    expect(
      within(reports).getByText("NIST-CSF-Report-v1.xlsx"),
    ).toBeInTheDocument();
    expect(
      within(reports).queryByText("network-inventory.csv"),
    ).not.toBeInTheDocument();
  });

  it("an automated draft is not a client upload either", async () => {
    serve([artifact("a9", "draft.docx", "automated_draft")]);
    render(<IntakeQueue clientId="00000000-0000-4000-8000-000000000001" />);
    await screen.findByRole("heading", { name: /^Generated reports \(1\)$/ });
    expect(
      within(section(/^Generated reports \(1\)$/)).getByText("draft.docx"),
    ).toBeInTheDocument();
    expect(
      within(section(/^Uploaded documents \(0\)$/)).getByText(
        "No documents uploaded yet",
      ),
    ).toBeInTheDocument();
  });

  it("shows both empty states when there are no artifacts", async () => {
    serve([]);
    render(<IntakeQueue clientId="00000000-0000-4000-8000-000000000001" />);
    await screen.findByRole("heading", { name: /^Generated reports \(0\)$/ });
    expect(
      within(section(/^Uploaded documents \(0\)$/)).getByText(
        "No documents uploaded yet",
      ),
    ).toBeInTheDocument();
    expect(
      within(section(/^Generated reports \(0\)$/)).getByText(
        "No reports generated yet",
      ),
    ).toBeInTheDocument();
  });

  // The readiness line must read the CLIENT's uploads. Asserted both ways so a
  // fix that hard-codes either answer goes red.
  async function readinessLine(): Promise<HTMLElement> {
    render(<IntakeQueue clientId="00000000-0000-4000-8000-000000000001" />);
    const label = await screen.findByText("Supporting documents uploaded");
    const li = label.closest("li");
    if (!li) throw new Error("readiness item has no <li>");
    return li;
  }

  it("does not tick 'Supporting documents uploaded' on generated reports alone", async () => {
    serve([artifact("a2", "NIST-CSF-Report-v1.pdf", "consultant_approved")]);
    const li = await readinessLine();
    expect(li).toHaveTextContent("no evidence to ground the assessment");
  });

  it("ticks 'Supporting documents uploaded' on a client upload", async () => {
    serve([artifact("a1", "network-inventory.csv", "client_upload")]);
    const li = await readinessLine();
    expect(li).not.toHaveTextContent("no evidence to ground the assessment");
  });
});
