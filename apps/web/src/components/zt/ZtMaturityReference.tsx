"use client";
import type { ZtFramework } from "@/lib/zt/types";

import type { JSX } from "react";

/**
 * Framework-appropriate link to the authoritative source that defines the
 * Zero Trust pillars and maturity levels. Shown beside the self-assessment so
 * a client (or consultant) can look up what each level means while answering.
 */
const REFERENCES: Record<
  ZtFramework,
  { href: string; label: string; describes: string }
> = {
  cisa_ztmm_2_0: {
    href: "https://www.cisa.gov/sites/default/files/2023-04/zero_trust_maturity_model_v2_508.pdf#page=9",
    label: "CISA Zero Trust Maturity Model v2 (PDF, opens at page 9)",
    describes: "defines each pillar and what each maturity stage looks like",
  },
  dod_ztra: {
    href: "https://dodcio.defense.gov/Portals/0/Documents/Library/DoD-ZTStrategy.pdf",
    label: "DoD Zero Trust Strategy (PDF)",
    describes:
      "describes the seven DoD pillars and the Target / Advanced Zero Trust maturity levels",
  },
};

export function ZtMaturityReference({
  framework,
}: {
  framework: ZtFramework;
}): JSX.Element | null {
  const ref = REFERENCES[framework];
  if (!ref) return null;
  return (
    <p className="text-sm text-ink-secondary">
      Not sure what a level means? The{" "}
      <a
        href={ref.href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-brand-600 underline hover:text-brand-700"
      >
        {ref.label}
      </a>{" "}
      {ref.describes}. Keep it open in another tab while you answer.
    </p>
  );
}
