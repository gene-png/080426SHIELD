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
 * The third bucket exists so nothing is dropped between two filters: the org
 * page does not render consultant uploads yet (#1067, copy pending), and a
 * bucket it ignores is visible in the code where two non-covering filters
 * are not.
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
