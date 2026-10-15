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
 * #1054 (IN-2), for #1119: a file a CONSULTANT uploads in a client's
 * workspaces (`client_upload` posted by an admin, as the Tech Debt Dropzone
 * does) is not the client's and not a generated report, so it gets its own
 * section on the org page. Copy approved verbatim (#736 6129929212). Every
 * artifact the API serves must appear in exactly one section.
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
  uploaded_by_role: AdminArtifactRow["uploaded_by_role"] = origin ===
  "client_upload"
    ? "client"
    : "admin",
): AdminArtifactRow {
  return {
    id,
    title,
    mime_type: "application/pdf",
    size_bytes: 2048,
    uploaded_by: "u1",
    uploaded_at: "2026-10-01T12:00:00Z",
    origin,
    uploaded_by_role,
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

const CLIENT = "00000000-0000-4000-8000-000000000001";

describe("IntakeQueue — consultant uploads (#1054, #1119)", () => {
  it("lists a consultant's upload under Consultant uploads, and only there", async () => {
    serve([
      artifact("a1", "network-inventory.csv", "client_upload"),
      artifact("a5", "consultant-inventory.csv", "client_upload", "admin"),
      artifact("a2", "NIST-CSF-Report-v1.pdf", "consultant_approved"),
    ]);
    render(<IntakeQueue clientId={CLIENT} />);
    await screen.findByRole("heading", { name: /^Consultant uploads \(1\)$/ });

    const consultant = section(/^Consultant uploads \(1\)$/);
    expect(
      within(consultant).getByText("consultant-inventory.csv"),
    ).toBeInTheDocument();
    expect(
      within(consultant).queryByText("network-inventory.csv"),
    ).not.toBeInTheDocument();
    expect(
      within(consultant).queryByText("NIST-CSF-Report-v1.pdf"),
    ).not.toBeInTheDocument();
  });

  it("puts every artifact in exactly one section", async () => {
    const rows = [
      artifact("a1", "network-inventory.csv", "client_upload"),
      artifact("a5", "consultant-inventory.csv", "client_upload", "admin"),
      artifact("a6", "consultant-diagram.pdf", "client_upload", "admin"),
      artifact("a2", "NIST-CSF-Report-v1.pdf", "consultant_approved"),
      artifact("a9", "draft.docx", "automated_draft"),
    ];
    serve(rows);
    render(<IntakeQueue clientId={CLIENT} />);
    await screen.findByRole("heading", { name: /^Consultant uploads \(2\)$/ });

    const sections = [
      section(/^Uploaded documents \(1\)$/),
      section(/^Consultant uploads \(2\)$/),
      section(/^Generated reports \(2\)$/),
    ];
    for (const row of rows) {
      const holders = sections.filter(
        (s) => within(s).queryByText(row.title) !== null,
      );
      expect(holders, row.title).toHaveLength(1);
      expect(screen.getAllByText(row.title), row.title).toHaveLength(1);
    }
  });

  it("shows the approved empty state when no consultant has uploaded", async () => {
    serve([
      artifact("a1", "network-inventory.csv", "client_upload"),
      artifact("a2", "NIST-CSF-Report-v1.pdf", "consultant_approved"),
    ]);
    render(<IntakeQueue clientId={CLIENT} />);
    await screen.findByRole("heading", { name: /^Consultant uploads \(0\)$/ });
    const consultant = section(/^Consultant uploads \(0\)$/);
    expect(
      within(consultant).getByText("No consultant uploads"),
    ).toBeInTheDocument();
    expect(
      within(consultant).getByText(
        "Files a consultant uploads in this organization's workspaces will appear here.",
      ),
    ).toBeInTheDocument();
  });

  it("does not show the empty state beside a listed upload", async () => {
    serve([
      artifact("a5", "consultant-inventory.csv", "client_upload", "admin"),
    ]);
    render(<IntakeQueue clientId={CLIENT} />);
    await screen.findByRole("heading", { name: /^Consultant uploads \(1\)$/ });
    expect(
      within(section(/^Consultant uploads \(1\)$/)).queryByText(
        "No consultant uploads",
      ),
    ).not.toBeInTheDocument();
  });
});
