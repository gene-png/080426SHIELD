import type { JSX, ReactNode } from "react";

/**
 * The internal-only band of Gene's UI page plan: "Admin-only content gets a
 * distinct band: "KENTRO ADMIN ONLY: never shown to the client"" (#736,
 * issuecomment-6115899349 rule 6; the "internal-only band" of v2,
 * issuecomment-6115981718). The text is Gene's, verbatim.
 *
 * It marks a block inside a page. SectionHeader's "Internal only" label says
 * where a whole page's content can go; the two are separate on purpose.
 */
export const INTERNAL_ONLY_BAND_TEXT =
  "KENTRO ADMIN ONLY: never shown to the client";

export function InternalOnlyBand({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <div
      data-testid="internal-only-band"
      className="flex flex-col rounded-md border-2 border-status-warning-fg"
    >
      <p className="bg-status-warning-fg px-4 py-1.5 text-sm font-bold text-ink-on-accent">
        {INTERNAL_ONLY_BAND_TEXT}
      </p>
      <div className="p-4">{children}</div>
    </div>
  );
}
