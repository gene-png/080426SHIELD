import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  DocumentsList,
  type ClientDeliverable,
  type ClientDeliverableListResponse,
} from "@/components/documents/DocumentsList";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { SkipToContent } from "@/components/site/SkipToContent";
import { ACTIVE_CLIENT_COOKIE, ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import Link from "next/link";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Documents" };

/** Minimal slice of GET /auth/me used to resolve the caller's tenant. */
interface MeResponse {
  role: "admin" | "client";
  client_id: string | null;
}

export default async function DocumentsPage(): Promise<JSX.Element> {
  const session = await auth();
  if (!session?.accessToken) {
    redirect("/sign-in?callbackUrl=/documents");
  }
  const token = session.accessToken;

  // Resolve whose released deliverables to show. Client-role users are pinned
  // to their own client_id server-side; a platform admin viewing a client uses
  // the active-client cookie (which apiFetch forwards as X-Client-Id below, so
  // the path id and the tenant header always agree). /auth/me is not
  // tenant-scoped, so suppress the cookie header on that call (clientId: "").
  const me = await apiFetch<MeResponse>("/auth/me", {
    bearer: token,
    clientId: "",
  });
  let clientId = me.client_id ?? undefined;
  if (!clientId) {
    clientId = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value ?? undefined;
  }

  // No resolvable tenant (a platform admin with no client selected): render the
  // empty state rather than a dead end. Client users always resolve a tenant.
  let items: ClientDeliverable[] = [];
  let hasRiskDashboard = false;
  if (clientId) {
    const data = await apiFetch<ClientDeliverableListResponse>(
      `/clients/${clientId}/deliverables`,
      { bearer: token },
    );
    items = data.items;

    // The Risk Register is client-level (not a per-service deliverable), so it
    // isn't in the list above. Probe it so we can surface a link when finalized.
    try {
      await apiFetch(`/clients/${clientId}/risk/dashboard`, { bearer: token });
      hasRiskDashboard = true;
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) throw err;
    }
  }

  return (
    <>
      <SkipToContent />
      <PublicHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10 outline-hidden"
      >
        <div>
          <h1 className="text-2xl font-semibold text-ink-primary">Documents</h1>
          <p className="mt-1 max-w-prose text-sm text-ink-secondary">
            What you&apos;ve received from your SHIELD engagement — reports and
            workbooks your analyst has released to you.
          </p>
        </div>
        {hasRiskDashboard ? (
          <Link
            href="/dashboards/risk"
            className="inline-flex w-fit items-center gap-2 rounded-md border border-brand-600 px-3 py-2 text-sm font-semibold text-brand-600 hover:bg-surface-sunken"
          >
            View Risk Register dashboard →
          </Link>
        ) : null}
        <DocumentsList items={items} />
      </main>
      <PublicFooter />
    </>
  );
}
