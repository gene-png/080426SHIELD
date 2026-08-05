import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AttackDashboard } from "@/components/dashboards/attack/AttackDashboard";
import { ApiError, apiFetch } from "@/lib/api";
import { resolveDashboardClientId } from "@/lib/dashboards/resolveClient";
import { auth } from "@/lib/auth/options";
import { SkipToContent } from "@/components/site/SkipToContent";
import type { AttackDashboardData } from "@/lib/dashboards/attack";

import type { JSX } from "react";

export const metadata: Metadata = { title: "ATT&CK Coverage Dashboard" };

/** Minimal slice of GET /auth/me used to resolve the caller's tenant. */
export default async function AttackDashboardPage({
  params,
}: {
  params: Promise<{ serviceId: string }>;
}): Promise<JSX.Element> {
  const { serviceId } = await params;
  const session = await auth();
  if (!session?.accessToken) {
    redirect(`/sign-in?callbackUrl=/dashboards/attack/${serviceId}`);
  }
  const token = session.accessToken;

  // Resolve the tenant exactly like /documents: client users are pinned; a
  // platform admin uses the active-client cookie (forwarded as X-Client-Id).
  // Issue 4: admins reaching this from a deliverable card may have no active
  // client cookie yet; the resolver falls back to the service's owning tenant.
  const clientId = await resolveDashboardClientId(token, serviceId);

  let data: AttackDashboardData | null = null;
  let notReleased = false;
  if (clientId) {
    try {
      data = await apiFetch<AttackDashboardData>(
        `/clients/${clientId}/attack/${serviceId}/dashboard`,
        { bearer: token, clientId },
      );
    } catch (err) {
      // 404 = no released report for this service yet (or wrong tenant). Show a
      // friendly not-available state rather than a dead end (§12 no-dead-ends).
      if (err instanceof ApiError && err.status === 404) {
        notReleased = true;
      } else {
        throw err;
      }
    }
  } else {
    notReleased = true;
  }

  if (!data) {
    return (
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 py-16 focus:outline-2 focus:outline-offset-4 focus:outline-brand-500"
      >
        <h1 className="text-2xl font-semibold text-ink-primary">
          Dashboard not available yet
        </h1>
        <p className="text-sm text-ink-secondary">
          {notReleased
            ? "This ATT&CK coverage report hasn't been released to your organization yet. It will appear here once your SHIELD analyst releases it."
            : "We couldn't load this dashboard."}
        </p>
        <Link
          href="/documents"
          className="text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          ← Back to documents
        </Link>
      </main>
    );
  }

  // The dashboards render their own dark shell, so they were returning no
  // <main> at all — the skip-to-content link had no destination here and the
  // page exposed no main landmark (found in the 2026-08-04 review). Matches
  // the eight app shells: one <main id="main-content"> with tabIndex={-1}.
  return (
    <>
      <SkipToContent />
      <main
        id="main-content"
        tabIndex={-1}
        className="focus:outline-2 focus:outline-offset-4 focus:outline-brand-500"
      >
        <AttackDashboard data={data} />
      </main>
    </>
  );
}
