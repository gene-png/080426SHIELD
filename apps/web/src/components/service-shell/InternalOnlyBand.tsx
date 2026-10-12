import type { JSX, ReactNode } from "react";

/**
 * The internal-only band of Gene's UI page plan: "Admin-only content gets a
 * distinct band: "KENTRO ADMIN ONLY: never shown to the client"" (#736,
 * issuecomment-6115899349 rule 6). The advisor ruled this text stays on every
 * internal-only surface (#736, issuecomment-6116519635).
 *
 * The band LABELS content; it does not protect it. Keeping the content away
 * from clients is the mounting page's job: an admin-only route, and an API
 * that never serves it to a client role. Wrapping client-reachable content in
 * this band would make the band's sentence false.
 *
 * It marks a block inside a page. SectionHeader's "Internal only" label says
 * where a whole section's content can go; the two are separate on purpose.
 *
 * Empty children THROW rather than render nothing: an empty band asserts admin
 * content that is not there, and a caller whose content is conditional should
 * render the band conditionally. Rendering nothing would hide that caller bug.
 */
export const INTERNAL_ONLY_BAND_TEXT =
  "KENTRO ADMIN ONLY: never shown to the client";

export function InternalOnlyBand({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  if (children === null || children === undefined || children === false) {
    throw new Error(
      "InternalOnlyBand: nothing to mark. Render the band only around content.",
    );
  }
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
