import Link from "next/link";

import type { JSX } from "react";

export function PublicFooter(): JSX.Element {
  return (
    <footer className="border-t border-border-subtle bg-surface-card">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 text-sm text-ink-secondary md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-semibold text-ink-primary">SHIELD by Kentro</p>
          <p className="mt-1 max-w-prose">
            Enterprise cybersecurity assessment platform. Operated by Kentro on
            behalf of customer assessments.
          </p>
        </div>
        <nav aria-label="Compliance" className="flex flex-col gap-1">
          <Link href="/accessibility" className="hover:text-ink-primary">
            Accessibility
          </Link>
          <Link href="/privacy" className="hover:text-ink-primary">
            Privacy
          </Link>
          <Link href="/security" className="hover:text-ink-primary">
            Security
          </Link>
        </nav>
      </div>
    </footer>
  );
}
