"use client";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import {
  addDomain,
  createClient,
  listClients,
  listDomains,
  removeDomain,
  type ClientSummary,
  type DomainRow,
} from "@/lib/admin/client";

import type { JSX } from "react";

export function ManagementView(): JSX.Element {
  const [clients, setClients] = React.useState<ClientSummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [newName, setNewName] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  // Monotonic request sequence: reload() fires on mount AND after onCreate. The
  // create form renders immediately, so a create can fire while the mount
  // reload is still in flight; without this guard the slow mount listClients()
  // could resolve last and clobber the post-create list, hiding the new client
  // (the T8 stale-fetch race). Only the newest reload may write state.
  const reloadSeq = React.useRef(0);

  const reload = React.useCallback(async () => {
    const seq = ++reloadSeq.current;
    try {
      const next = await listClients();
      if (seq === reloadSeq.current) setClients(next);
      else
        console.debug(
          `[ManagementView] discarded stale clients reload (seq ${seq}, latest ${reloadSeq.current})`,
        );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load clients.");
    }
  }, []);

  React.useEffect(() => {
    void (async () => {
      await reload();
    })();
  }, [reload]);

  async function onCreate(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createClient({ legal_name: newName.trim() });
      setNewName("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create client.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Create a client</CardTitle>
        </CardHeader>
        <CardBody>
          <form
            onSubmit={(e) => void onCreate(e)}
            className="flex flex-wrap gap-3"
          >
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Legal name, e.g. Atlas Defense"
              aria-label="New client legal name"
              className="min-w-[16rem] flex-1 rounded-md border border-border bg-surface-card px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={busy || !newName.trim()}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:opacity-60"
            >
              {busy ? "Creating…" : "Create client"}
            </button>
          </form>
        </CardBody>
      </Card>

      {error ? (
        <p className="text-sm text-status-danger-fg" role="alert">
          {error}
        </p>
      ) : null}

      {clients === null ? (
        <p className="text-sm text-ink-tertiary">Loading clients…</p>
      ) : clients.length === 0 ? (
        <Card>
          <CardBody>
            <p className="text-sm text-ink-secondary">
              No clients yet. Create one above, then approve its email domain so
              its team can register.
            </p>
          </CardBody>
        </Card>
      ) : (
        <ul className="flex flex-col gap-4">
          {clients.map((c) => (
            <li key={c.id}>
              <ClientRow client={c} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ClientRow({ client }: { client: ClientSummary }): JSX.Element {
  const [domains, setDomains] = React.useState<DomainRow[] | null>(null);
  const [newDomain, setNewDomain] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  // Same stale-fetch guard as the parent: the add-domain form renders before
  // the mount reload resolves, so an add can race the mount listDomains(). Only
  // the newest reload may write state.
  const reloadSeq = React.useRef(0);

  const reload = React.useCallback(async () => {
    const seq = ++reloadSeq.current;
    try {
      const next = await listDomains(client.id);
      if (seq === reloadSeq.current) setDomains(next);
      else
        console.debug(
          `[ManagementView] discarded stale domains reload (seq ${seq}, latest ${reloadSeq.current})`,
        );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load domains.");
    }
  }, [client.id]);

  React.useEffect(() => {
    void (async () => {
      await reload();
    })();
  }, [reload]);

  async function onAdd(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!newDomain.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await addDomain(client.id, newDomain.trim());
      setNewDomain("");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add domain.");
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(did: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await removeDomain(client.id, did);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove domain.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{client.legal_name}</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
            Approved email domains
          </p>
          {domains === null ? (
            <p className="mt-1 text-sm text-ink-tertiary">Loading…</p>
          ) : domains.length === 0 ? (
            <p className="mt-1 text-sm text-ink-secondary">
              None yet — add one so this client&apos;s team can self-register.
            </p>
          ) : (
            <ul className="mt-1 flex flex-wrap gap-2">
              {domains.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center gap-2 rounded-md border border-border-subtle bg-surface-sunken px-2 py-1 text-sm"
                >
                  <span className="font-mono">{d.domain}</span>
                  <button
                    type="button"
                    onClick={() => void onRemove(d.id)}
                    disabled={busy}
                    aria-label={`Remove ${d.domain}`}
                    className="text-ink-tertiary hover:text-status-danger-fg"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <form onSubmit={(e) => void onAdd(e)} className="flex flex-wrap gap-2">
          <input
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            placeholder="company.com"
            aria-label={`New domain for ${client.legal_name}`}
            className="min-w-[12rem] rounded-md border border-border bg-surface-card px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !newDomain.trim()}
            className="rounded-md border border-border bg-surface-card px-3 py-1.5 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:opacity-60"
          >
            Add domain
          </button>
        </form>
        {error ? (
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
