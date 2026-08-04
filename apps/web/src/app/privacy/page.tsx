import type { Metadata } from "next";

import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-semibold text-ink-primary">Privacy</h1>
        <p className="mt-4 text-ink-secondary">
          SHIELD by Kentro is single-tenant per assessment. Each deployment is
          operationally isolated; no client assessment data leaves the
          deployment boundary except through the PII-redaction layer when an AI
          extraction is explicitly approved by the consultant.
        </p>
        <p className="mt-4 text-ink-secondary">
          Full privacy notice and data-processing terms ship with the assessment
          contract. For questions before Phase 6 ships the public-facing notice,
          email{" "}
          <a
            href="mailto:privacy@kentro.local"
            className="font-medium text-brand-500"
          >
            privacy@kentro.local
          </a>
          .
        </p>
      </main>
      <PublicFooter />
    </>
  );
}
