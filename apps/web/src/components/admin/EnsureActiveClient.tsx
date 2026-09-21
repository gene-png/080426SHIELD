"use client";
import * as React from "react";

import type { JSX } from "react";

/**
 * Aligns the active-client cookie to a workspace's owning tenant before its
 * children render. Admin workspace data is tenant-scoped via
 * X-Client-Id (the active-client cookie), but the workspace URL only carries a
 * serviceId. Without this, opening a workspace whose client isn't the one
 * currently selected in the switcher makes every tenant-scoped call 400/404.
 *
 * Resolves the service's client_id, sets it active if needed, then renders.
 */
export function EnsureActiveClient({
  serviceId,
  children,
}: {
  serviceId: string;
  children: React.ReactNode;
}): JSX.Element {
  const [ready, setReady] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`/api/proxy/admin/services/${serviceId}`, {
          cache: "no-store",
        });
        if (!res.ok) {
          throw new Error(`Couldn't resolve this workspace (${res.status}).`);
        }
        const svc = (await res.json()) as { client_id?: string };
        if (!svc.client_id) throw new Error("Service has no client.");

        // An ADVISORY read: its only job is to decide whether the POST
        // below is redundant. A failure here is safe to absorb because it
        // falls through to the write -- and the write is now CHECKED, which
        // it was not when this sentence was first written.
        //
        // The original claim was that the POST "throws into the catch at the
        // bottom and surfaces to the user". `fetch` rejects only on network
        // failure: a 403 or a 500 resolves, so the cookie stayed unset,
        // `setReady(true)` rendered the children, and every tenant-scoped
        // call underneath 400'd or 404'd under a misleading per-workspace
        // error. The exemption rested on a check that did not exist, and the
        // sentence is what would have stopped the next reader adding it.
        //
        // Written as an explicit handler rather than `.catch(() => null)`
        // because the two are indistinguishable to any reader, and to the
        // guard: a considered fallback and a silent swallow look identical
        // when the fallback is written as an arrow returning null. Saying
        // WHY here is what makes it an exemption rather than an oversight.
        let cur: { active?: string } | null = null;
        try {
          const r = await fetch("/api/active-client", { cache: "no-store" });
          cur = (await r.json()) as { active?: string };
        } catch {
          // Leave `cur` null so the branch below re-asserts the active
          // client. Not silence: the write is the recovery, and its failure
          // is surfaced.
          cur = null;
        }
        if (cur?.active !== svc.client_id) {
          const set = await fetch("/api/active-client", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clientId: svc.client_id }),
          });
          if (!set.ok) {
            // FAIL CLOSED. Without this the cookie is unset, the children
            // render anyway, and every tenant-scoped call underneath fails
            // with a message about the wrong thing. A workspace that cannot
            // establish its client has not opened.
            throw new Error(
              `Couldn't open this workspace for its client (${set.status}).`,
            );
          }
        }
        if (!cancelled) setReady(true);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Couldn't open workspace.",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [serviceId]);

  if (error) {
    return (
      <p role="alert" className="text-sm text-status-danger-fg">
        {error}
      </p>
    );
  }
  if (!ready) {
    return (
      <p className="text-sm text-ink-tertiary" aria-live="polite">
        Opening workspace…
      </p>
    );
  }
  return <>{children}</>;
}
