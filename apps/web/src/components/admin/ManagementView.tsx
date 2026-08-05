"use client";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import {
  addDomain,
  archiveClient,
  createClient,
  listClientUsers,
  listClients,
  listDomains,
  removeDomain,
  setUserActive,
  type AdminUserRow,
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
              <ClientRow client={c} onArchived={() => void reload()} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Issue 3: users inside a tenant, with deactivate/reactivate.
 *
 * Deactivation — not deletion — is the removal primitive: sign-in refuses an
 * inactive account, so access stops immediately while the rows the user
 * authored (assessments, messages, audit entries) stay intact and the action
 * stays reversible. Deactivated users therefore remain listed, labelled, with
 * a Reactivate control; hiding them would make the action one-way from the UI.
 */
function UserList({ clientId }: { clientId: string }): JSX.Element {
  const [users, setUsers] = React.useState<AdminUserRow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  // UX finding 20: deactivating signs the user out immediately and blocks the
  // next login, but it was a single unguarded click while archive and
  // key-removal both confirm. Reactivation is not destructive and stays direct.
  const [confirmingId, setConfirmingId] = React.useState<string | null>(null);

  const reloadSeq = React.useRef(0);
  const reload = React.useCallback(async () => {
    const seq = ++reloadSeq.current;
    try {
      const next = await listClientUsers(clientId);
      if (seq === reloadSeq.current) setUsers(next);
      else
        console.debug(
          `[ManagementView] discarded stale users reload (seq ${seq}, latest ${reloadSeq.current})`,
        );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    }
  }, [clientId]);

  React.useEffect(() => {
    void (async () => {
      await reload();
    })();
  }, [reload]);

  async function onToggle(u: AdminUserRow): Promise<void> {
    setBusyId(u.id);
    setError(null);
    try {
      await setUserActive(u.id, !u.is_active);
      setConfirmingId(null);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
        Users
      </p>
      {users === null ? (
        <p className="mt-1 text-sm text-ink-tertiary">Loading…</p>
      ) : users.length === 0 ? (
        <p className="mt-1 text-sm text-ink-secondary">
          No users have registered against this client yet.
        </p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1">
          {users.map((u) => (
            <li
              key={u.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border-subtle bg-surface-sunken px-3 py-2 text-sm"
            >
              <span className="min-w-0">
                <span className="font-medium text-ink-primary">{u.email}</span>
                {u.display_name ? (
                  <span className="text-ink-tertiary"> · {u.display_name}</span>
                ) : null}
                {!u.is_active ? (
                  <span className="ml-2 rounded bg-status-warning-bg px-1.5 py-0.5 text-xs font-semibold text-status-warning-fg">
                    Deactivated
                  </span>
                ) : null}
              </span>
              {u.is_active && confirmingId === u.id ? (
                <span className="flex shrink-0 flex-wrap items-center gap-2 text-xs">
                  <span className="text-ink-secondary">
                    Deactivate {u.email}? They are signed out immediately and
                    cannot sign in again. Their data is kept and you can
                    reactivate them.
                  </span>
                  <button
                    type="button"
                    onClick={() => void onToggle(u)}
                    disabled={busyId === u.id}
                    className="rounded-md bg-status-danger-fg px-3 py-1 text-xs font-semibold text-ink-on-accent disabled:opacity-60"
                  >
                    {busyId === u.id ? "Deactivating…" : "Yes, deactivate"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingId(null)}
                    disabled={busyId === u.id}
                    className="rounded-md border border-border bg-surface-card px-3 py-1 text-xs font-semibold text-ink-primary hover:bg-surface-sunken"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    u.is_active ? setConfirmingId(u.id) : void onToggle(u)
                  }
                  disabled={busyId === u.id}
                  className={
                    "shrink-0 rounded-md border px-3 py-1 text-xs font-semibold disabled:opacity-60 " +
                    (u.is_active
                      ? "border-status-danger-border text-status-danger-fg hover:bg-status-danger-bg"
                      : "border-border bg-surface-card text-ink-primary hover:bg-surface-sunken")
                  }
                >
                  {busyId === u.id
                    ? "Saving…"
                    : u.is_active
                      ? "Deactivate"
                      : "Reactivate"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error ? (
        <p className="mt-1 text-sm text-status-danger-fg" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ClientRow({
  client,
  onArchived,
}: {
  client: ClientSummary;
  onArchived: () => void;
}): JSX.Element {
  const [domains, setDomains] = React.useState<DomainRow[] | null>(null);
  const [newDomain, setNewDomain] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  // Archive is destructive-looking and cross-tenant, so it is gated behind an
  // explicit confirm step rather than a single click. No window.confirm(): a
  // native modal dialog blocks the page and cannot be styled or tested well.
  const [confirmingArchive, setConfirmingArchive] = React.useState(false);

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

  async function onArchive(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await archiveClient(client.id);
      setConfirmingArchive(false);
      onArchived();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to archive client.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{client.legal_name}</CardTitle>
          {confirmingArchive ? (
            <span className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-ink-secondary">
                Archive {client.legal_name}? Its data is kept and this can be
                undone.
              </span>
              <button
                type="button"
                onClick={() => void onArchive()}
                disabled={busy}
                className="rounded-md bg-status-danger-fg px-3 py-1 text-xs font-semibold text-ink-on-accent disabled:opacity-60"
              >
                {busy ? "Archiving…" : "Yes, archive"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmingArchive(false)}
                disabled={busy}
                className="rounded-md border border-border bg-surface-card px-3 py-1 text-xs font-semibold text-ink-primary hover:bg-surface-sunken"
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingArchive(true)}
              aria-label={`Archive ${client.legal_name}`}
              className="rounded-md border border-status-danger-border px-3 py-1 text-xs font-semibold text-status-danger-fg hover:bg-status-danger-bg"
            >
              Archive client
            </button>
          )}
        </div>
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
        <UserList clientId={client.id} />
        {error ? (
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
