"use client";

/**
 * Active-client dropdown for the admin role.
 *
 * Loads the platform-wide client list from /api/proxy/admin/clients,
 * displays the currently-active tenant (read from the active_client_id
 * cookie via a server prop), and on change posts to /api/active-client
 * to update the cookie. Refreshes the route tree afterwards so server
 * components re-render with the new tenant scope.
 *
 * Hidden for client-role users (their tenant is server-pinned).
 */

import { useEffect, useState, type JSX } from "react";
import { useRouter } from "next/navigation";

interface ClientSummary {
  id: string;
  legal_name: string;
  dba_name: string | null;
}

interface ClientListResponse {
  clients: ClientSummary[];
}

export function ClientSwitcher(): JSX.Element | null {
  const router = useRouter();
  const [clients, setClients] = useState<ClientSummary[] | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        // Load the active cookie value and the client list in parallel.
        const [activeRes, listRes] = await Promise.all([
          fetch("/api/active-client", { cache: "no-store" }),
          fetch("/api/proxy/admin/clients", { cache: "no-store" }),
        ]);
        if (cancelled) return;
        if (activeRes.ok) {
          const j = (await activeRes.json()) as { active?: string | null };
          setActive(typeof j?.active === "string" ? j.active : null);
        }
        if (!listRes.ok) {
          setClients([]);
          return;
        }
        const json = (await listRes.json()) as Partial<ClientListResponse>;
        // Defensive: error envelopes don't have `clients`. Coerce to [].
        setClients(Array.isArray(json?.clients) ? json.clients : []);
      } catch {
        if (!cancelled) setClients([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onChange(next: string): Promise<void> {
    setLoading(true);
    try {
      const res = await fetch("/api/active-client", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId: next || null }),
      });
      if (res.ok) {
        setActive(next || null);
        router.refresh();
      }
    } finally {
      setLoading(false);
    }
  }

  if (clients === null) {
    return (
      <span className="text-xs text-ink-tertiary" aria-label="Loading clients">
        Clients…
      </span>
    );
  }
  if (clients.length === 0) {
    return <span className="text-xs text-ink-tertiary">No clients yet</span>;
  }

  return (
    <label className="flex items-center gap-2 text-xs">
      <span className="text-ink-tertiary">Client</span>
      <select
        value={active ?? ""}
        onChange={(e) => void onChange(e.target.value)}
        disabled={loading}
        className="rounded-md border border-border-subtle bg-surface-card px-2 py-1 text-ink-primary"
        aria-label="Active client"
      >
        <option value="">— pick one —</option>
        {clients.map((c) => (
          <option key={c.id} value={c.id}>
            {c.dba_name ? `${c.dba_name} (${c.legal_name})` : c.legal_name}
          </option>
        ))}
      </select>
    </label>
  );
}
