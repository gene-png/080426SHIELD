import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import { MessageThread } from "@/components/messages/MessageThread";
import { CsfSelfAssessment } from "@/components/self-assessment/CsfSelfAssessment";
import { ZtSelfAssessment } from "@/components/self-assessment/ZtSelfAssessment";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { auth } from "@/lib/auth/options";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Self-assessment" };

const COPY: Record<string, { title: string; blurb: string }> = {
  nist_csf: {
    title: "NIST CSF 2.0 self-assessment",
    blurb:
      "Tell us where your organization stands today across the CSF 2.0 outcomes, and the maturity tier you're aiming for.",
  },
  zero_trust_cisa: {
    title: "Zero Trust self-assessment — CISA ZTMM 2.0",
    blurb:
      "Rate your organization across the CISA Zero Trust pillars and set the maturity stage you're aiming for.",
  },
  zero_trust_dod: {
    title: "Zero Trust self-assessment — DoD ZTRA",
    blurb:
      "Rate your organization across the DoD Zero Trust pillars and set the maturity stage you're aiming for.",
  },
};

export default async function SelfAssessmentPage(props: {
  params: Promise<{ serviceId: string }>;
  searchParams: Promise<{ type?: string }>;
}): Promise<JSX.Element> {
  const searchParams = await props.searchParams;
  const params = await props.params;
  const session = await auth();
  const type = searchParams.type ?? "";
  if (!session) {
    const cb = encodeURIComponent(
      `/self-assessment/${params.serviceId}?type=${type}`,
    );
    redirect(`/sign-in?callbackUrl=${cb}`);
  }

  const copy = COPY[type];

  return (
    <>
      <PublicHeader />
      <main className="mx-auto w-full max-w-4xl px-6 py-10">
        <header className="mb-8 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
            Organizational self-assessment
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">
            {copy?.title ?? "Self-assessment"}
          </h1>
          {copy ? (
            <p className="max-w-prose text-ink-secondary">{copy.blurb}</p>
          ) : null}
        </header>

        {type === "nist_csf" ? (
          <CsfSelfAssessment serviceId={params.serviceId} />
        ) : type === "zero_trust_cisa" ? (
          <ZtSelfAssessment
            serviceId={params.serviceId}
            framework="cisa_ztmm_2_0"
          />
        ) : type === "zero_trust_dod" ? (
          <ZtSelfAssessment serviceId={params.serviceId} framework="dod_ztra" />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Open this from your intake confirmation</CardTitle>
            </CardHeader>
            <CardBody>
              <p className="text-sm text-ink-secondary">
                We couldn&apos;t tell which assessment to load. Head back to
                your intake confirmation and pick a self-assessment to start.
              </p>
            </CardBody>
          </Card>
        )}

        {copy ? (
          <div className="mt-8">
            <MessageThread serviceId={params.serviceId} />
          </div>
        ) : null}
      </main>
      <PublicFooter />
    </>
  );
}
