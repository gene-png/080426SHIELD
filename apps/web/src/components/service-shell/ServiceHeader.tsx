import Link from "next/link";

import type { JSX } from "react";

/**
 * The persistent service header, plan v2 rule 5 (#736,
 * issuecomment-6116093149): "shows the service name, the version and status,
 * the stage, and one line: "Next: {action}" as a link".
 *
 * "Next:" is Gene's. The version, status and stage are the caller's text, and
 * so are their labels: none is approved yet, so each value renders as the
 * caller writes it (for example "v2", "Draft", "Review"), with no fixed
 * label in front. When nothing is next the Next line is omitted rather than
 * filled with unapproved copy.
 *
 * The service title is a link to the service's Overview, not a heading: the
 * section's one h1 is in SectionHeader.
 */
export function ServiceHeader({
  serviceTitle,
  overviewHref,
  version,
  status,
  stage,
  next,
}: {
  serviceTitle: string;
  overviewHref: string;
  version: string;
  status: string;
  stage: string;
  next: { text: string; href: string } | null;
}): JSX.Element {
  for (const [name, value] of [
    ["version", version],
    ["status", status],
    ["stage", stage],
  ] as const) {
    if (!value.trim()) {
      throw new Error(`ServiceHeader: a blank ${name}; rule 5 shows it.`);
    }
  }
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-border-subtle bg-surface-card px-6 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link
          href={overviewHref}
          className="text-base font-semibold text-ink-primary hover:text-brand-600"
        >
          {serviceTitle}
        </Link>
        <span
          data-testid="service-header-version"
          className="text-sm text-ink-secondary"
        >
          {version}
        </span>
        <span
          data-testid="service-header-status"
          className="text-sm text-ink-secondary"
        >
          {status}
        </span>
        <span
          data-testid="service-header-stage"
          className="text-sm text-ink-secondary"
        >
          {stage}
        </span>
      </div>
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
