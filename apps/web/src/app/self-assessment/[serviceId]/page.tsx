import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { apiFetch } from "@/lib/api";

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
  let type = searchParams.type ?? "";
  if (!session) {
    const cb = encodeURIComponent(
      `/self-assessment/${params.serviceId}?type=${type}`,
    );
    redirect(`/sign-in?callbackUrl=${cb}`);
  }

  // UX finding 12: without ?type= this page dead-ended, even though the service
  // record identifies the assessment. Every in-app link passes the param, so
  // this path is reached by bookmarked, copied or emailed URLs — no user error.
  // Resolve it from the client's own assessments before giving up.
  let resolvedType = type;
  if (!COPY[resolvedType] && session.accessToken) {
    try {
      const assessments = await apiFetch<
        Array<{ service_id: string; service_type: string }>
      >("/intake/engagements", { bearer: session.accessToken });
      resolvedType =
        assessments.find((a) => a.service_id === params.serviceId)
          ?.service_type ?? resolvedType;
    } catch {
      // Fall through to the recovery card below — never a hard failure.
    }
  }
  type = resolvedType;

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
              <CardTitle>We couldn&apos;t open that assessment</CardTitle>
            </CardHeader>
            <CardBody className="flex flex-col items-start gap-3">
              <p className="text-sm text-ink-secondary">
                This link doesn&apos;t match an assessment on your account. It
                may have been completed, or it may belong to a different
                organization.
              </p>
              <Link
                href="/assessments"
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
              >
                Go to your assessments
              </Link>
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
