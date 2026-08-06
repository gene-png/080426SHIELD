import type { Metadata } from "next";
import Link from "next/link";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { SkipToContent } from "@/components/site/SkipToContent";
import {
  SERVICE_DESCRIPTIONS,
  SERVICE_LABELS,
  type ServiceType,
} from "@/lib/intake/types";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Help" };

/**
 * IA appendix: "Messages / Help — consultant messages, service explanations,
 * support and accessibility contact."
 *
 * Messages already had a home; the explanations and the contact routes did not.
 * A client could see "MITRE ATT&CK Coverage Mapping" on their dashboard with
 * nowhere to find out what it is.
 *
 * The service copy is imported from `lib/intake/types`, the SAME map the intake
 * picker reads — so a service cannot be described one way when you choose it
 * and another way when you look it up.
 */

/** Order matches the intake picker, so the two pages read the same way. */
const SERVICE_ORDER: ServiceType[] = [
  "tech_debt",
  "zero_trust_cisa",
  "zero_trust_dod",
  "nist_csf",
  "attack_coverage",
  "consultation",
];

export default function HelpPage(): JSX.Element {
  return (
    <>
      <SkipToContent />
      <PublicHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-4xl flex-col gap-8 px-6 py-10 focus:outline-2 focus:outline-offset-4 focus:outline-brand-500"
      >
        <header className="space-y-1">
          <h1 className="text-3xl font-semibold text-ink-primary">Help</h1>
          <p className="max-w-prose text-sm text-ink-secondary">
            What each service does, and how to reach a person when you need one.
          </p>
        </header>

        <section aria-labelledby="services-heading" className="space-y-3">
          <h2
            id="services-heading"
            className="text-lg font-semibold text-ink-primary"
          >
            The services
          </h2>
          <ul className="flex flex-col gap-3">
            {SERVICE_ORDER.map((service) => (
              <li key={service}>
                <Card>
                  <CardHeader>
                    <CardTitle>{SERVICE_LABELS[service]}</CardTitle>
                  </CardHeader>
                  <CardBody>
                    <p className="text-sm text-ink-secondary">
                      {SERVICE_DESCRIPTIONS[service]}
                    </p>
                  </CardBody>
                </Card>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="contact-heading" className="space-y-3">
          <h2
            id="contact-heading"
            className="text-lg font-semibold text-ink-primary"
          >
            Getting help
          </h2>
          <Card>
            <CardBody className="flex flex-col gap-3 text-sm">
              <p className="text-ink-secondary">
                <span className="font-semibold text-ink-primary">
                  Questions about your engagement
                </span>{" "}
                — message your analyst directly. They see everything you send
                against your engagement.
              </p>
              <Link
                href="/messages"
                className="self-start font-semibold text-brand-600 hover:text-brand-500"
              >
                Open messages →
              </Link>
              <p className="text-ink-secondary">
                <span className="font-semibold text-ink-primary">
                  Accessibility
                </span>{" "}
                — our conformance status, known gaps, and how to report a
                barrier.
              </p>
              <Link
                href="/accessibility"
                className="self-start font-semibold text-brand-600 hover:text-brand-500"
              >
                Accessibility statement →
              </Link>
              <p className="text-ink-secondary">
                <span className="font-semibold text-ink-primary">
                  Account and sign-in
                </span>{" "}
                — update your profile, password, and multi-factor settings.
              </p>
              <Link
                href="/account"
                className="self-start font-semibold text-brand-600 hover:text-brand-500"
              >
                Account settings →
              </Link>
            </CardBody>
          </Card>
        </section>
      </main>
      <PublicFooter />
    </>
  );
}
