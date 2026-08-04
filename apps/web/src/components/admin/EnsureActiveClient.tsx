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

        const cur = await fetch("/api/active-client", { cache: "no-store" })
          .then((r) => r.json())
          .catch(() => null);
        if (cur?.active !== svc.client_id) {
          await fetch("/api/active-client", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clientId: svc.client_id }),
          });
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
