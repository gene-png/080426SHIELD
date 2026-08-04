import type { Metadata } from "next";

import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Security" };

export default function SecurityPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-3xl font-semibold text-ink-primary">Security</h1>
        <p className="mt-4 text-ink-secondary">
          SHIELD is targeted at FedRAMP Moderate / High and runs in AWS GovCloud
          or Azure Government. The redaction layer in front of every AI call is
          the primary data-protection boundary for v1; egress is audited with a
          hashed record of every redacted payload.
        </p>
        <p className="mt-4 text-ink-secondary">
          To report a vulnerability, email{" "}
          <a
            href="mailto:security@kentro.local"
            className="font-medium text-brand-500"
          >
            security@kentro.local
          </a>
          . Please do not file public GitHub issues for security reports.
        </p>
      </main>
      <PublicFooter />
    </>
  );
}
