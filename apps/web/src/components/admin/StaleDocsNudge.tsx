import type { JSX } from "react";
/**
 * Work Order C3: a regenerate nudge shown when an AI run has changed scores
 * since the documents were last generated. Inline colours so it renders
 * regardless of theme tokens.
 */
export function StaleDocsNudge({
  stale,
}: {
  stale?: boolean;
}): JSX.Element | null {
  if (!stale) return null;
  return (
    <div
      role="status"
      className="rounded-md border px-3 py-2 text-sm"
      style={{
        backgroundColor: "#fffbeb",
        color: "#92400e",
        borderColor: "#fde68a",
      }}
    >
      The AI has updated scores since the documents were last generated.
      Regenerate the deliverable / export to refresh them.
    </div>
  );
}
