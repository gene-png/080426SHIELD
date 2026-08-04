import Link from "next/link";

import type { JSX } from "react";

/**
 * Breadcrumb trail (Navigation_Spec §3). Every segment except the last is a
 * link; the current page is the last, non-link segment.
 */
export interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }): JSX.Element {
  return (
    <nav aria-label="Breadcrumb" className="text-sm">
      <ol className="flex flex-wrap items-center gap-1 text-ink-tertiary">
        {items.map((c, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${c.label}-${i}`} className="flex items-center gap-1">
              {c.href && !last ? (
                <Link
                  href={c.href}
                  className="hover:text-ink-primary hover:underline"
                >
                  {c.label}
                </Link>
              ) : (
                <span
                  className={
                    last ? "font-medium text-ink-secondary" : undefined
                  }
                  aria-current={last ? "page" : undefined}
                >
                  {c.label}
                </span>
              )}
              {!last ? <span aria-hidden="true">/</span> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
