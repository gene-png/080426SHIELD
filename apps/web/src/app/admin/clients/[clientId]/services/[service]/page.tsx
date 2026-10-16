import { notFound, redirect } from "next/navigation";
import { Suspense } from "react";

import { RiskRegisterDashboard } from "@/components/admin/risk/RiskRegisterDashboard";
import {
  kindForSlug,
  RISK_REGISTER_SLUG,
  riskRegisterHref,
  sectionHref,
} from "@/components/service-shell/frameRoutes";
import { SHELL_COPY } from "@/components/service-shell/shellCopy";
import { loadClientFrame } from "@/lib/admin/client-route";

import type { JSX } from "react";

/**
 * T6: a service URL with no section goes to its Overview.
 *
 * The Risk Register has no sections yet (its track adds them), so this route
 * renders the existing dashboard unchanged. That dashboard picks its client
 * from `?client`, with its own picker, so the page keeps `?client` and the
 * path's client equal: it adds a missing `?client`, and a `?client` naming
 * another client (the dashboard's picker after Apply) moves to that client's
 * path, whose layout checks it.
 */
export default async function ServicePage(props: {
  params: Promise<{ clientId: string; service: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<JSX.Element> {
  const { clientId, service } = await props.params;
  const query = await props.searchParams;

  if (service === RISK_REGISTER_SLUG) {
    const asked = typeof query.client === "string" ? query.client : "";
    const target = asked || clientId;
    if (asked !== clientId)
      redirect(
        `${riskRegisterHref(target)}?client=${encodeURIComponent(target)}`,
      );
    await loadClientFrame(clientId);
    return (
      <Suspense
        fallback={
          <h1 className="text-2xl font-semibold text-ink-primary">
            {SHELL_COPY.riskRegister}
          </h1>
        }
      >
        <RiskRegisterDashboard />
      </Suspense>
    );
  }

  const kind = kindForSlug(service);
  if (!kind) notFound();
  const id = typeof query.service === "string" ? query.service : null;
  redirect(sectionHref(clientId, kind, "overview", id));
}
