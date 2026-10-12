import type { JSX } from "react";

/**
 * #1058 (TD-2): tells a client to list each product separately rather than as
 * a suite, because Tech Debt and ATT&CK assess each product's job on its own.
 * Copy is Gene's draft on #736 (6115250609); the MITRE variant replaces only
 * the first two sentences of the first body line (ruling 6115345112).
 */

export type SuiteBannerVariant = "tech_debt" | "attack_coverage";

const FIRST_LINE: Record<SuiteBannerVariant, string> = {
  tech_debt:
    "Many licenses are suites that bundle several products. Please list every product, module or capability you use on its own line, not just the suite name. Each one does a different job, and we assess each job separately.",
  attack_coverage:
    "Many security tools come as suites. Please list every product, module or capability that detects, prevents or responds to threats on its own line, not just the suite name. Each one does a different job, and we assess each job separately.",
};

/**
 * Which variant a set of selected services gets. Both selected shows ONE
 * banner with the Tech Debt text (ruling 6115345112); neither shows none.
 */
export function suiteBannerVariant(
  services: readonly string[] | null | undefined,
): SuiteBannerVariant | null {
  if (!services) return null;
  if (services.includes("tech_debt")) return "tech_debt";
  if (services.includes("attack_coverage")) return "attack_coverage";
  return null;
}

export function SuiteListingBanner({
  variant,
}: {
  variant: SuiteBannerVariant;
}): JSX.Element {
  return (
    <section
      aria-labelledby="suite-listing-heading"
      className="flex flex-col gap-3 rounded-md border-2 border-brand-500 bg-brand-50 p-5 text-base text-ink-primary"
    >
      <h4
        id="suite-listing-heading"
        className="text-lg font-semibold text-ink-primary"
      >
        List each product separately, not as a suite.
      </h4>
      <p>{FIRST_LINE[variant]}</p>
      <p>
        <strong>Example:</strong> Microsoft 365 G5 is one license, but it
        includes separate products such as Microsoft Defender for Endpoint
        (protects computers and servers), Microsoft Entra ID P2 (manages sign-in
        and identity) and Microsoft Purview (protects and classifies sensitive
        data). List each one you use, and say whether it is in use or purchased
        but not deployed.
      </p>
      <p>Questions? Contact your Kentro representative.</p>
    </section>
  );
}
