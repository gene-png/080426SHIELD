import Link from "next/link";

import type { JSX } from "react";

/**
 * The section bar of Gene's UI page plan v2 (#736, issuecomment-6115981718):
 * "Sections with their own URLs, not ARIA tabs". Every section is a real link
 * to its own page, so a section can be bookmarked, shared and reloaded.
 *
 * The labels and their order are Gene's, verbatim (plan v2, #736
 * issuecomment-6116093149). Recommendations is the link text alone; its
 * admin-only marker is a separate "KENTRO ADMIN ONLY" badge BESIDE the link,
 * outside it, so it is not part of the link's name. The nav is named "Service
 * sections" (both rulings, #736 issuecomment-6116092992). The URLs are NOT
 * decided here: the caller supplies `hrefFor`, so the route shape is chosen by
 * the page that mounts this (the Tech Debt pilot), not by the shared piece.
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

/** Whether `key` is a KENTRO ADMIN ONLY section (only Recommendations, today). */
export function isAdminOnlySection(key: SectionKey): boolean {
  return SECTIONS.some((s) => s.key === key && s.adminOnly);
}

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
  // A CALLER bug, never data-driven. `current` is always one of the nine
  // keys, so this one check also refuses omitting every section: that omits
  // the current one too.
  if (omit.includes(current)) {
    throw new Error(
      `SectionBar: the current section "${current}" is omitted, so no link could be marked current.`,
    );
  }
  const shown = SECTIONS.filter((s) => !omit.includes(s.key)).map((s) => {
    const href = hrefFor(s.key);
    // Trimmed: a whitespace-only href is as empty as "" (a CALLER bug).
    if (!href.trim()) {
      throw new Error(
        `SectionBar: hrefFor("${s.key}") returned an empty href; every section needs its own URL.`,
      );
    }
    return { ...s, href };
  });
  return (
    <nav
      aria-label="Service sections"
      className="border-b border-border-subtle bg-surface-card px-6"
    >
      <ul className="flex flex-wrap gap-x-1">
        {shown.map((section) => {
          const active = section.key === current;
          return (
            <li key={section.key} className="flex items-center">
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={
                  "inline-block border-b-2 px-3 py-2 text-sm font-medium " +
                  (active
                    ? "border-brand-500 text-brand-600"
                    : "border-transparent text-ink-secondary hover:text-ink-primary")
                }
              >
                {section.label}
              </Link>
              {section.adminOnly ? (
                <span
                  data-admin-badge
                  className="rounded-sm bg-status-warning-fg px-1.5 py-0.5 text-xs font-bold text-ink-on-accent"
                >
                  KENTRO ADMIN ONLY
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
