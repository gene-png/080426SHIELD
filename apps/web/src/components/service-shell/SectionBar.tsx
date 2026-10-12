import Link from "next/link";

import type { JSX } from "react";

/**
 * The section bar of Gene's UI page plan v2 (#736, issuecomment-6115981718):
 * "Sections with their own URLs, not ARIA tabs". Every section is a real link
 * to its own page, so a section can be bookmarked, shared and reloaded.
 *
 * The labels and their order are Gene's, verbatim (plan v2, #736
 * issuecomment-6116093149). Recommendations is the link text alone; its
 * admin-only marker is a separate "KENTRO ADMIN ONLY" badge beside it, and the
 * nav is named "Service sections" (both rulings, #736
 * issuecomment-6116092992). The URLs are NOT decided here: the caller supplies
 * `hrefFor`, so the route shape is chosen by the page that mounts this (the
 * Tech Debt pilot), not by the shared piece.
 */
export const SECTIONS = [
  { key: "overview", label: "Overview", adminOnly: false },
  { key: "inputs", label: "Inputs", adminOnly: false },
  { key: "ai-draft", label: "AI draft", adminOnly: false },
  { key: "review", label: "Review", adminOnly: false },
  { key: "analysis", label: "Analysis", adminOnly: false },
  { key: "generate", label: "Generate", adminOnly: false },
  { key: "quality-check", label: "Quality check", adminOnly: false },
  {
    key: "approve-and-release",
    label: "Approve and release",
    adminOnly: false,
  },
  { key: "recommendations", label: "Recommendations", adminOnly: true },
] as const;

export type SectionKey = (typeof SECTIONS)[number]["key"];

export function SectionBar({
  current,
  hrefFor,
  omit = [],
}: {
  current: SectionKey;
  hrefFor: (key: SectionKey) => string;
  /** Sections this service does not have, e.g. CSF and ZT fold Inputs into AI draft. */
  omit?: readonly SectionKey[];
}): JSX.Element {
  const shown = SECTIONS.filter((s) => !omit.includes(s.key));
  return (
    <nav
      aria-label="Service sections"
      className="border-b border-border-subtle bg-surface-card px-6"
    >
      <ul className="flex flex-wrap gap-x-1">
        {shown.map((section) => {
          const active = section.key === current;
          return (
            <li key={section.key}>
              <Link
                href={hrefFor(section.key)}
                aria-current={active ? "page" : undefined}
                className={
                  "inline-block border-b-2 px-3 py-2 text-sm font-medium " +
                  (active
                    ? "border-brand-500 text-brand-600"
                    : "border-transparent text-ink-secondary hover:text-ink-primary")
                }
              >
                <span data-section-label>{section.label}</span>
                {section.adminOnly ? (
                  <span
                    data-admin-badge
                    className="ml-2 rounded-sm bg-status-warning-fg px-1.5 py-0.5 text-xs font-bold text-ink-on-accent"
                  >
                    KENTRO ADMIN ONLY
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
