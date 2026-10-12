import Link from "next/link";

import type { JSX } from "react";

/**
 * The persistent service header of Gene's UI page plan v2 (#736,
 * issuecomment-6115981718): on every section, "showing "Next: …"".
 *
 * "Next:" is Gene's. What follows it is the caller's, and rule 3 of the plan
 * binds it: a link says where it goes. When nothing is next the line is
 * omitted rather than filled with copy nobody has approved.
 *
 * The service title is a link to the service's Overview, not a heading: the
 * page's one h1 is the section title, in SectionHeader.
 */
export function ServiceHeader({
  serviceTitle,
  overviewHref,
  next,
}: {
  serviceTitle: string;
  overviewHref: string;
  next: { text: string; href: string } | null;
}): JSX.Element {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border-subtle bg-surface-card px-6 py-3">
      <Link
        href={overviewHref}
        className="text-base font-semibold text-ink-primary hover:text-brand-600"
      >
        {serviceTitle}
      </Link>
      {next ? (
        <p
          data-testid="service-header-next"
          className="text-sm text-ink-secondary"
        >
          <span className="font-semibold text-ink-primary">Next:</span>{" "}
          <Link
            href={next.href}
            className="font-medium text-brand-600 underline hover:text-brand-700"
          >
            {next.text}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
