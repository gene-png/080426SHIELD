import type { AdminArtifactRow } from "./types";

/**
 * #1054: a tenant's artifacts, split on what the API serves (stored origin and
 * uploader role), never on a filename. Every artifact lands in exactly one
 * bucket:
 *
 * - `clientUploads`: `client_upload` from a client-role user. Only these count
 *   as "the client attached it".
 * - `consultantUploads`: `client_upload` from an admin. The upload route stamps
 *   every file `client_upload`, and the Tech Debt Dropzone posts to it as the
 *   admin.
 * - `generatedReports`: every other origin (a deliverable's files, written at
 *   finalize or export).
 *
 * One split rather than separate filters, so nothing can fall between them:
 * the org page renders each bucket in its own section (#1119).
 */
export interface ArtifactBuckets {
  clientUploads: AdminArtifactRow[];
  consultantUploads: AdminArtifactRow[];
  generatedReports: AdminArtifactRow[];
}

export function splitArtifacts(
  artifacts: readonly AdminArtifactRow[],
): ArtifactBuckets {
  const buckets: ArtifactBuckets = {
    clientUploads: [],
    consultantUploads: [],
    generatedReports: [],
  };
  for (const a of artifacts) {
    if (a.origin !== "client_upload") {
      buckets.generatedReports.push(a);
    } else if (a.uploaded_by_role === "client") {
      buckets.clientUploads.push(a);
    } else {
      buckets.consultantUploads.push(a);
    }
  }
  return buckets;
}
