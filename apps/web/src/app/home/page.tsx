import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { ClientDeliverableListResponse } from "@/components/results/ResultsList";
import { HomeDashboard, type HomePanel } from "@/components/home/HomeDashboard";
import type { ValueSummary } from "@/components/home/ValueLoopCard";
import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";
import { SkipToContent } from "@/components/site/SkipToContent";
import { ACTIVE_CLIENT_COOKIE, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth/options";
import type { AssessmentResponse } from "@/lib/intake/types";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Home" };

/** Minimal slice of GET /auth/me used to greet + resolve the caller's tenant. */
interface MeResponse {
  role: "admin" | "client";
  client_id: string | null;
  display_name: string | null;
  email: string;
}

/** Slice of GET /messages/inbox — only the unread total feeds "waiting on you". */
interface InboxResponse {
  unread_total: number;
}

/**
 * The signed-in client landing page (Master Spec §6.4). Admins are steered to
 * /admin from `/`; a client — or an admin viewing a selected tenant — lands
 * here. All data is fetched server-side (no client-side mount fetch, so no
 * request-sequence guard needed) and handed to the presentational
 * HomeDashboard. §6.4: this surface shows phase and next steps only, never
 * scoring math, audit internals, or raw AI output.
 */
export default async function HomePage(): Promise<JSX.Element> {
  const session = await auth();
  if (!session?.accessToken) {
    redirect("/sign-in?callbackUrl=/home");
  }
  const token = session.accessToken;

  // Resolve whose engagement to show. Client-role users are pinned to their own
  // client_id server-side; a platform admin viewing a client uses the
  // active-client cookie (forwarded as X-Client-Id by apiFetch). /auth/me is not
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
  // no-data guidance state rather than a dead end. Client users always resolve.
  let deliverables: ClientDeliverableListResponse["items"] = [];
  let engagements: AssessmentResponse[] = [];
  let unreadMessages = 0;
  let valueSummary: ValueSummary | null = null;
  const unavailable: HomePanel[] = [];
  if (clientId) {
    // `/auth/me` ABOVE IS DELIBERATELY NOT IN THIS SET, and saying so because
    // an unstated exemption reads as an oversight. It is still a bare `await`,
    // so its failure still takes the page down -- correctly: there is no
    // identity, so there is no page to degrade INTO. The four below are
    // different: each renders a panel that means something on its own.
    //
    // FOUR PANELS THAT RENDER INDEPENDENTLY MUST FAIL INDEPENDENTLY (#236).
    //
    // This was one `Promise.all` with no `catch`, and there is no `error.tsx`
    // anywhere under `apps/web/src/app`, so ANY one of the four rejecting took
    // down the WHOLE page -- including the client's list of released reports,
    // which has nothing to do with the endpoint that failed. The four dashboard
    // pages already wrap their fetch and render a friendly not-available state
    // (no dead ends); `/home` did not.
    //
    // THE PART THAT WAS THE ACTUAL WORK, and why this sat open: a degraded
    // panel must not be indistinguishable from an EMPTY one. Passing `[]`, `0`
    // and `null` on failure would make the page assert "you have no reports",
    // "no engagements" and "no unread messages" -- claims about the client's
    // account, made from an error. Missing data defaults to UNCONFIRMED, never
    // to confirmed, so each failure is recorded and rendered as "could not
    // load" rather than as an absence.
    const [deliverableData, engagementData, inbox, summary] =
      await Promise.allSettled([
        apiFetch<ClientDeliverableListResponse>(
          `/clients/${clientId}/deliverables`,
          { bearer: token },
        ),
        apiFetch<AssessmentResponse[]>("/intake/engagements", {
          bearer: token,
        }),
        apiFetch<InboxResponse>("/messages/inbox", { bearer: token }),
        apiFetch<ValueSummary>(`/clients/${clientId}/value-summary`, {
          bearer: token,
        }),
      ]);

    if (deliverableData.status === "fulfilled") {
      deliverables = deliverableData.value.items;
    } else {
      unavailable.push("deliverables");
    }
    if (engagementData.status === "fulfilled") {
      engagements = engagementData.value;
    } else {
      unavailable.push("engagements");
    }
    if (inbox.status === "fulfilled") {
      unreadMessages = inbox.value.unread_total;
    } else {
      unavailable.push("messages");
    }
    if (summary.status === "fulfilled") {
      valueSummary = summary.value;
    } else {
      unavailable.push("value");
    }
  }

  const greetingName = me.display_name?.trim() || me.email;

  return (
    <>
      <SkipToContent />
      <PublicHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10 focus:outline-2 focus:outline-offset-4 focus:outline-brand-500"
      >
        <HomeDashboard
          greetingName={greetingName}
          deliverables={deliverables}
          engagements={engagements}
          unreadMessages={unreadMessages}
          valueSummary={valueSummary}
          unavailable={unavailable}
        />
      </main>
      <PublicFooter />
    </>
  );
}
