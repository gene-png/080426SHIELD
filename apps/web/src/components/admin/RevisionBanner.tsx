import { REVISION_COPY } from "@/lib/revisions/copy";
import { fill } from "@/lib/revisions/fill";

import type { RevisionInfo } from "@/lib/revisions/types";
import type { JSX } from "react";

export interface RevisionBannerProps {
  /** The record's status; the banner shows on a revision DRAFT only. */
  status: string;
  /** `revision` from the assessment response; null unless a revision minted it. */
  revision: RevisionInfo | null | undefined;
}

/** V4's first sentence, derived from the approved V4 rather than retyped. */
function catalogSentence(): string {
  const v4 = REVISION_COPY.V4;
  return v4.slice(0, v4.indexOf(". ") + 2);
}

/**
 * #1120: on a revision draft, who started it and why (V5); that it uses the
 * current scoring rules when its source was approved under earlier ones (V3);
 * and, for ATT&CK, the techniques the current catalog dropped (V4).
 */
export function RevisionBanner({
  status,
  revision,
}: RevisionBannerProps): JSX.Element | null {
  if (status !== "draft" || !revision) return null;
  const v = revision.from_version;
  const date = new Date(revision.started_at).toLocaleDateString();
  const codes = revision.retired_codes;
  return (
    <div
      role="status"
      className="flex flex-col gap-1 rounded-md border border-status-info-fg bg-status-info-bg px-4 py-3 text-sm text-ink-primary"
    >
      <p>
        {fill(REVISION_COPY.V5, {
          v,
          name: revision.started_by_name,
          date,
          reason: revision.reason,
        })}
      </p>
      {revision.rules_changed ? <p>{fill(REVISION_COPY.V3, { v })}</p> : null}
      {codes.length === 1 ? (
        <p>
          {catalogSentence() +
            fill(REVISION_COPY.V4_ONE, { v, code: codes[0] })}
        </p>
      ) : codes.length > 1 ? (
        <p>
          {fill(REVISION_COPY.V4, {
            n: codes.length,
            v,
            codes: codes.join(", "),
          })}
        </p>
      ) : null}
    </div>
  );
}
