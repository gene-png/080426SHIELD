/**
 * #1120: reading a "Start a revision" refusal. The API answers every refusal
 * with a typed 409 (`{error: {reason, message}}`); `draft_open` (V6 and V8)
 * means a draft already exists for the service, so the workspace re-reads the
 * service's latest record and shows that draft beneath the dialog.
 */
export const DRAFT_OPEN_REASON = "draft_open";

/** The typed `reason` of a proxy error's payload, or null when it has none. */
export function refusalReason(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) return null;
  const error = (payload as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return null;
  const reason = (error as { reason?: unknown }).reason;
  return typeof reason === "string" ? reason : null;
}
