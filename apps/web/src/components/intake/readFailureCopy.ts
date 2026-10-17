import { readFailureReason, serverReasonCode } from "@/lib/describe-save-error";

/**
 * #1225: the server's sentence for a failed READ of the intake upload list,
 * or null for the caller's own copy. One rule for the three surfaces that
 * read it (Step 5, Step 6, the admin documents panel), so they cannot drift.
 *
 * Only a TYPED sentence (D-016 `{reason, message}`) is copy meant for a
 * reader. A plain-string api `detail` arrives in the envelope with no
 * `reason` and is internal text ("X-Client-Id header is required for this
 * role.", "Client-role user is not bound to a client."), so it is withheld.
 * `readFailureReason` also withholds #550's write sentence (RR-2) and any
 * `schema_*` reason.
 */
export function typedReadFailure(err: unknown): string | null {
  return serverReasonCode(err) !== null ? readFailureReason(err) : null;
}
