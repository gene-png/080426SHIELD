import Link from "next/link";

import { requireText } from "./guards";

import type { JSX } from "react";

/**
 * The persistent service header, plan v2 rule 5 (#736,
 * issuecomment-6116093149): "shows the service name, the version and status,
 * the stage, and one line: "Next: {action}" as a link".
 *
 * "Next:" is Gene's. The labels "Version", "Status" and "Stage" are the
 * advisor's, approved verbatim (#736, issuecomment-6128447366); the values
 * under them are the caller's text (for example "v2", "Draft", "Review"). A
 * term/definition list joins label and value with no punctuation of its own.
 * When nothing is next the Next line is omitted rather than filled with
 * unapproved copy.
 *
 * The service title is a link to the service's Overview, not a heading: the
 * section's one h1 is in SectionHeader.
 *
 * Every string it renders must be non-blank, or it throws. A blank title,
 * href or next text is a CALLER bug. A blank version, status or stage may be
 * DATA-driven if the page passes an API field straight through; the page
 * should map a missing value to its own text before calling.
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
    ["serviceTitle", serviceTitle],
    ["overviewHref", overviewHref],
    ["version", version],
    ["status", status],
    ["stage", stage],
  ] as const) {
    requireText("ServiceHeader", name, value);
  }
  if (next) {
    requireText("ServiceHeader", "next.text", next.text);
    requireText("ServiceHeader", "next.href", next.href);
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
        <dl className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <HeaderFact testId="service-header-version" label="Version">
            {version}
          </HeaderFact>
          <HeaderFact testId="service-header-status" label="Status">
            {status}
          </HeaderFact>
          <HeaderFact testId="service-header-stage" label="Stage">
            {stage}
          </HeaderFact>
        </dl>
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

function HeaderFact({
  testId,
  label,
  children,
}: {
  testId: string;
  label: string;
  children: string;
}): JSX.Element {
  return (
    <div data-testid={testId} className="flex items-center gap-1">
      <dt className="text-ink-tertiary">{label}</dt>
      <dd className="text-ink-secondary">{children}</dd>
    </div>
  );
}
