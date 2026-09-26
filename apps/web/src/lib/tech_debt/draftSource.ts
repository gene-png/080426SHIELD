import type { CapabilityList } from "./types";

/**
 * #644: the one document an open draft's rows were extracted from, or null.
 *
 * Mirrors the API's `_draft_source_artifact_id`, which is what decides whether
 * "Extract from this" returns the draft or refuses: null when the list is not
 * an open draft, when no row names a document (a hand-included row names none),
 * or when rows name more than one. The API refuses in every null case, so this
 * only ever adds a marker; it never hides a refusal.
 */
export function draftSourceArtifactId(
  list: CapabilityList | null,
): string | null {
  if (list === null || list.status !== "draft") return null;
  const sources = new Set(
    list.items
      .map((item) => item.source_artifact_id)
      .filter((id): id is string => id !== null && id !== undefined),
  );
  return sources.size === 1 ? [...sources][0] : null;
}
