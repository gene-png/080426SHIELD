import { describe, expect, it } from "vitest";

import { splitArtifacts } from "./artifactBuckets";
import type { AdminArtifactRow } from "./types";

/**
 * #1054: the intake org page splits a tenant's artifacts by stored origin and
 * uploader role. Every artifact must land in exactly ONE bucket, so a row the
 * page does not show (consultant uploads, whose section's copy is pending) is
 * still accounted for rather than silently dropped by two filters that do not
 * cover the space between them.
 *
 * The origins and roles below are spelled out from `ArtifactOrigin` in
 * `apps/api/app/models/artifact.py` and `UserRole` in
 * `apps/api/app/models/user.py`, not read from the module under test.
 */

const ORIGINS = [
  "client_upload",
  "automated_draft",
  "consultant_approved",
] as const;
const ROLES = ["admin", "client"] as const;

function artifact(
  origin: AdminArtifactRow["origin"],
  role: AdminArtifactRow["uploaded_by_role"],
): AdminArtifactRow {
  return {
    id: `${origin}-${role}`,
    title: `${origin} by ${role}.pdf`,
    mime_type: "application/pdf",
    size_bytes: 1,
    uploaded_by: "u",
    uploaded_at: "2026-10-12T00:00:00Z",
    origin,
    uploaded_by_role: role,
  };
}

const ALL = ORIGINS.flatMap((o) => ROLES.map((r) => artifact(o, r)));

describe("splitArtifacts", () => {
  it("puts every origin and role pair in exactly one bucket", () => {
    const b = splitArtifacts(ALL);
    const placed = [
      ...b.clientUploads,
      ...b.generatedReports,
      ...b.consultantUploads,
    ].map((a) => a.id);
    expect(placed).toHaveLength(ALL.length);
    expect(new Set(placed)).toEqual(new Set(ALL.map((a) => a.id)));
  });

  it("counts only a client-role client_upload as the client's", () => {
    expect(splitArtifacts(ALL).clientUploads.map((a) => a.id)).toEqual([
      "client_upload-client",
    ]);
  });

  it("puts a consultant's client_upload in its own bucket", () => {
    expect(splitArtifacts(ALL).consultantUploads.map((a) => a.id)).toEqual([
      "client_upload-admin",
    ]);
  });

  it("puts every non-upload origin under generated reports, whoever wrote it", () => {
    expect(
      splitArtifacts(ALL)
        .generatedReports.map((a) => a.id)
        .sort(),
    ).toEqual([
      "automated_draft-admin",
      "automated_draft-client",
      "consultant_approved-admin",
      "consultant_approved-client",
    ]);
  });
});
