import type { Metadata } from "next";

import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Accessibility" };

export default function AccessibilityPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-semibold text-ink-primary">
          Accessibility
        </h1>
        <p className="mt-4 text-ink-secondary">
          SHIELD by Kentro is built to meet WCAG 2.1 AA. Keyboard navigation,
          screen-reader support, color contrast, and reduced-motion are
          first-class requirements - not afterthoughts.
        </p>
        <p className="mt-4 text-ink-secondary">
          A complete accessibility statement (including the third-party audit
          summary and a contact for accessibility issues) ships with Phase 6
          hardening. To report an issue before then, email{" "}
          <a
            href="mailto:accessibility@kentro.local"
            className="font-medium text-brand-500"
          >
            accessibility@kentro.local
          </a>
          .
        </p>
      </main>
      <PublicFooter />
    </>
  );
}
