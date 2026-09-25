import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { RiskDashboard } from "@/components/dashboards/risk/RiskDashboard";
import { ACTIVE_CLIENT_COOKIE, ApiError, apiFetch } from "@/lib/api";
import {
  dashboardLoadReason,
  isCatalogWithheld,
} from "@/lib/describe-save-error";
import { auth } from "@/lib/auth/options";
import { SkipToContent } from "@/components/site/SkipToContent";
import type { RiskDashboardData } from "@/lib/dashboards/risk";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Risk Register Dashboard" };

interface MeResponse {
  role: "admin" | "client";
  client_id: string | null;
}

export default async function RiskDashboardPage(): Promise<JSX.Element> {
  const session = await auth();
  if (!session?.accessToken) {
    redirect(`/sign-in?callbackUrl=/dashboards/risk`);
  }
  const token = session.accessToken;

  const me = await apiFetch<MeResponse>("/auth/me", {
    bearer: token,
    clientId: "",
  });
  let clientId = me.client_id ?? undefined;
  if (!clientId) {
    clientId = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value ?? undefined;
  }

  let data: RiskDashboardData | null = null;
  let notReleased = false;
  // #556: finalized, but built from an ATT&CK report on another catalog, so the
  // API withholds it (typed 409). Rendered with the server's sentence rather
  // than rethrown into Next's error page.
  let withheld = false;
  // The server's typed explanation, where it sent one (#244).
  let reason: string | null = null;
  if (clientId) {
    try {
      data = await apiFetch<RiskDashboardData>(
        `/clients/${clientId}/risk/dashboard`,
        {
          bearer: token,
        },
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        notReleased = true;
        // #244: keep the server's OWN sentence. A 404 here has more than one
        // cause and the API already distinguishes them -- `_unresolved_parent`
        // returns a typed reason written specifically NOT to say "no released
        // report yet", because there IS one and what is missing is the link
        // saying which assessment it was built from. Keying the copy on the
        // STATUS discarded that and printed the very sentence the typed
        // message was written to avoid.
        // #318: the server's sentence only where it says something this page's
        // copy does not. `serverReason` here rendered the API's
        // developer-facing 'No released X report for this service yet.'
        // over the client copy below, in the page's MOST COMMON state --
        // the typed reason overriding the normal case instead of the
        // exceptional one. The decision lives in one place so the five
        // dashboards cannot drift.
        reason = dashboardLoadReason(err);
      } else if (isCatalogWithheld(err)) {
        withheld = true;
        reason = dashboardLoadReason(err);
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
          {withheld
            ? "Risk Register withheld"
            : "Risk Register not available yet"}
        </h1>
        <p className="text-sm text-ink-secondary">
          {reason ??
            (withheld
              ? "Your Risk Register is withheld."
              : notReleased
                ? "Your Risk Register hasn't been finalized yet. It will appear here once your SHIELD analyst generates and finalizes it."
                : "We couldn't load your Risk Register.")}
        </p>
        <Link
          href="/results"
          className="text-sm font-medium text-brand-600 hover:text-brand-700"
        >
          ← Back to results
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
        <RiskDashboard data={data} />
      </main>
    </>
  );
}
