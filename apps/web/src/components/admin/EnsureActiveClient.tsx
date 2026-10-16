"use client";
import * as React from "react";

import type { JSX } from "react";

import { WorkspaceClientProvider } from "./workspaceClient";

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
  // The client resolved FOR a service (#1262). Derived per service rather
  // than reset on change: when `serviceId` changes, the stored one no longer
  // matches and the children wait, so an upload can never be filed under the
  // previous service's client while the next one resolves.
  const [resolved, setResolved] = React.useState<{
    serviceId: string;
    clientId: string;
  } | null>(null);
  const clientId =
    resolved && resolved.serviceId === serviceId ? resolved.clientId : null;
  // #1266: the error belongs to the service whose lookup failed, the same
  // derivation as the client, so a new service never shows the last one's.
  const [failed, setFailed] = React.useState<{
    serviceId: string;
    message: string;
  } | null>(null);
  const error =
    failed && failed.serviceId === serviceId ? failed.message : null;

  React.useEffect(() => {
    let cancelled = false;
    // #1266: cleanup also ABORTS this run's requests, so a cookie write
    // already in flight when the service changes cannot land afterwards.
    const controller = new AbortController();
    const { signal } = controller;
    void (async () => {
      try {
        const res = await fetch(`/api/proxy/admin/services/${serviceId}`, {
          cache: "no-store",
          signal,
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
        // the children rendered anyway, and every tenant-scoped
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
          const r = await fetch("/api/active-client", {
            cache: "no-store",
            signal,
          });
          cur = (await r.json()) as { active?: string };
        } catch {
          // Leave `cur` null so the branch below re-asserts the active
          // client. Not silence: the write is the recovery, and its failure
          // is surfaced.
          cur = null;
        }
        // #1266: ONE gate, right before the cookie write: a run a newer
        // service superseded (during the lookup or the advisory read)
        // writes nothing, so its write cannot land after the current one's
        // and name the old client.
        if (cancelled) return;
        if (cur?.active !== svc.client_id) {
          const set = await fetch("/api/active-client", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clientId: svc.client_id }),
            signal,
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
        if (!cancelled) {
          setResolved({ serviceId, clientId: svc.client_id });
          // #1266: this service now opened, so an earlier failure of it
          // no longer stands.
          setFailed((f) => (f && f.serviceId === serviceId ? null : f));
        }
      } catch (err) {
        if (!cancelled) {
          setFailed({
            serviceId,
            message:
              err instanceof Error ? err.message : "Couldn't open workspace.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [serviceId]);

  if (error) {
    return (
      <p role="alert" className="text-sm text-status-danger-fg">
        {error}
      </p>
    );
  }
  if (clientId === null) {
    return (
      <p className="text-sm text-ink-tertiary" aria-live="polite">
        Opening workspace…
      </p>
    );
  }
  return (
    <WorkspaceClientProvider clientId={clientId}>
      {children}
    </WorkspaceClientProvider>
  );
}
