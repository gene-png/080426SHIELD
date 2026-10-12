import { requireText } from "./guards";
import { isAdminOnlySection, type SectionKey } from "./SectionBar";

import type { JSX } from "react";

/**
 * The section header of Gene's UI page plan v2, rules 2 and 6 (#736,
 * issuecomment-6116093149): the title; "What this section is for", in one
 * plain sentence; "What you can do here", in one to three short bullets; and
 * its visibility state. v2 supersedes v1's "What this page is for".
 *
 * The two labels and the three visibility labels are Gene's, verbatim. The
 * released label's format, "Released to client: v{n}, {d Mon yyyy}", is the
 * advisor's ruling (#736, issuecomment-6116519635). The sentence and bullets
 * are the caller's, and go to Gene verbatim per section. A term/definition
 * list adds no punctuation of its own, so no unapproved character ships
 * between a label and its text.
 *
 * Refused, loudly. CALLER bugs: an admin-only section (Recommendations)
 * labelled anything but "internal"; a bullet count outside one to three; a
 * blank title, purpose or bullet. DATA-driven, from the API, which a mounting
 * page must expect until apps/web has an error boundary: an unknown
 * visibility, and a released label without a whole version from 1 or without
 * a parseable release instant that names its zone.
 */
export type Visibility = "internal" | "client-preview" | "released";

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  internal: "Internal only",
  "client-preview": "Client preview",
  released: "Released to client",
};

const VISIBILITY_CLASS: Record<Visibility, string> = {
  internal:
    "border-status-warning-border bg-status-warning-bg text-status-warning-fg",
  "client-preview":
    "border-status-info-border bg-status-info-bg text-status-info-fg",
  released:
    "border-status-success-border bg-status-success-bg text-status-success-fg",
};

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * "12 Oct 2026" for a release INSTANT, in UTC. No existing helper gives this
 * form: `formatDate` (dashboards/shared.tsx) gives "Oct 12, 2026", and
 * `formatDateOnly` (lib/dates.ts) uses the viewer's locale for calendar dates.
 * UTC matches every other surface showing a release instant (see the zone note
 * in dashboards/shared.tsx); built from the UTC parts, not Intl, so the month
 * is always three letters (en-GB writes "Sept").
 */
// An instant must be an ISO date and time ending in a zone: without one,
// `new Date` reads the string in the viewer's local time, and the UTC date
// shown could be a day off. YYYY-MM-DDThh:mm, seconds and fractions optional
// (22:30Z is accepted), then Z, +hh:mm or +hhmm. Case-sensitive: a lowercase
// "t" or "z" parses differently across engines.
const ZONED =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$/;

export function releaseDateText(releasedAt: string): string {
  requireText("SectionHeader", "release date", releasedAt);
  if (!ZONED.test(releasedAt.trim())) {
    throw new Error(
      `SectionHeader: release date "${releasedAt}" has no zone after an ISO time (YYYY-MM-DDThh:mm, seconds optional, then Z, ±hh:mm or ±hhmm; uppercase T and Z), so it is not an instant.`,
    );
  }
  const d = new Date(releasedAt);
  if (Number.isNaN(d.getTime())) {
    throw new Error(
      `SectionHeader: release date "${releasedAt}" is not a parseable instant.`,
    );
  }
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function visibilityText(
  visibility: Visibility,
  release: { version: number; releasedAt: string } | undefined,
): string {
  if (!Object.hasOwn(VISIBILITY_LABEL, visibility)) {
    throw new Error(`SectionHeader: unknown visibility "${visibility}".`);
  }
  if (visibility !== "released") return VISIBILITY_LABEL[visibility];
  if (!release || !Number.isInteger(release.version) || release.version < 1) {
    throw new Error(
      'SectionHeader: "released" needs the released version (a whole number from 1) and its date.',
    );
  }
  return `${VISIBILITY_LABEL.released}: v${release.version}, ${releaseDateText(release.releasedAt)}`;
}

export function SectionHeader({
  section,
  title,
  purpose,
  canDo,
  visibility,
  release,
}: {
  section: SectionKey;
  title: string;
  purpose: string;
  /** One to three short bullets (plan v2, rule 2). */
  canDo: readonly string[];
  visibility: Visibility;
  /** Required when `visibility` is "released": what the client can see now. */
  release?: { version: number; releasedAt: string };
}): JSX.Element {
  if (isAdminOnlySection(section) && visibility !== "internal") {
    throw new Error(
      `SectionHeader: the admin-only section "${section}" can only be labelled "internal", not "${visibility}".`,
    );
  }
  const label = visibilityText(visibility, release);
  requireText("SectionHeader", "title", title);
  requireText("SectionHeader", "purpose", purpose);
  if (canDo.length < 1 || canDo.length > 3) {
    throw new Error(
      `SectionHeader "${title}": "What you can do here" takes one to three bullets (plan v2, rule 2), got ${canDo.length}.`,
    );
  }
  canDo.forEach((item) => requireText("SectionHeader", "bullet", item));
  return (
    <header className="flex flex-col gap-3 px-6 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-primary">
          {title}
        </h1>
        <span
          data-testid="section-visibility"
          className={
            "rounded-full border px-2.5 py-0.5 text-xs font-semibold " +
            VISIBILITY_CLASS[visibility]
          }
        >
          {label}
        </span>
      </div>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
        <dt className="font-semibold text-ink-primary">
          What this section is for
        </dt>
        <dd className="text-ink-secondary">{purpose}</dd>
        <dt className="font-semibold text-ink-primary">What you can do here</dt>
        <dd className="text-ink-secondary">
          <ul className="list-disc pl-5">
            {canDo.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </dd>
      </dl>
    </header>
  );
}
