"use client";
import * as React from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { AdminClientPicker } from "@/components/admin/AdminClientPicker";
import {
  resolveClientChoice,
  useClientReads,
  type ClientChoice,
  type ClientOption,
} from "@/lib/admin/client-choice";
import { leaveTo, reloadPage } from "@/lib/admin/navigate";

import type { JSX, ReactNode } from "react";

/**
 * RR-2 (for #1121): the frame the Risk Register, Deliverables and Messages
 * pages share. It owns, ABOVE the body that is keyed on the client:
 * - the two mount-time reads and the derived choice (§3.1a);
 * - the header, in every state (CLAUDE.md: the page identity in every branch);
 * - the picker and Apply (§3.3);
 * - the line each non-chosen state shows (§7 strings 4–8, 11, 17a, 17b);
 * - the in-flight lock the body reports, and the `leaving` lock Apply sets.
 */

/** §7, approved verbatim (#736 6130838759, 6133670854). */
export const CLIENT_LINES = {
  listFailed: "The client list could not be loaded, so no client is selected.",
  stale:
    "The client saved in this browser is no longer listed. Choose a client above, then select Show this client.",
  cookieFailed:
    "SHIELD could not check which client is saved in this browser. Choose a client above, then select Show this client.",
  linkUnlisted:
    "The client named in this page's link is not in the client list. Choose a client above, then select Show this client.",
  linkEmpty:
    "This page's link does not name a client. Choose a client above, then select Show this client.",
  leaving: (label: string) =>
    `Opening ${label}. If this page does not change, reload it, then choose the client again.`,
} as const;

export interface ClientScopedBodyProps {
  client: ClientOption;
  /** Apply was pressed: every control that starts work is disabled. */
  leaving: boolean;
  /** The body's work in flight, which locks the picker. */
  onBusyChange: (busy: boolean) => void;
}

function useUrlClient(): { present: boolean; value: string | null } {
  // Outside the App Router this is null; the pages always sit inside it.
  const params = useSearchParams();
  return {
    present: params?.has("client") ?? false,
    value: params?.get("client") ?? null,
  };
}

function clientsOf(choice: ClientChoice): ClientOption[] | null {
  switch (choice.kind) {
    case "list_failed":
    case "none":
      return null;
    default:
      return choice.clients;
  }
}

export function ClientScopedPage({
  header,
  noClient,
  loadingText = "Loading…",
  children,
}: {
  /** The page's header: its h1, and its chosen-only subtitle. */
  header: (chosen: ClientOption | null) => ReactNode;
  /** `unchosen`: the page's "Pick a client first" state (strings 4–6). */
  noClient: ReactNode;
  loadingText?: string;
  children: (props: ClientScopedBodyProps) => ReactNode;
}): JSX.Element {
  const pathname = usePathname();
  const url = useUrlClient();
  const { list, cookie } = useClientReads();
  const choice = resolveClientChoice(list, cookie, url);
  const [leaving, setLeaving] = React.useState<ClientOption | null>(null);
  const [bodyBusy, setBodyBusy] = React.useState(false);
  // Set once per mount: a full page load gives a new one, a soft navigation
  // does not. The e2e reads it to tell the two apart.
  const [mountedAt] = React.useState(
    () => `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );

  // §0j finding 5: a page restored from the back/forward cache could carry a
  // `leaving` lock with nothing to clear it. Reload it instead.
  React.useEffect(() => {
    const onShow = (ev: PageTransitionEvent) => {
      if (ev.persisted) reloadPage();
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, []);

  const onBusyChange = React.useCallback((busy: boolean) => {
    setBodyBusy(busy);
  }, []);

  function apply(client: ClientOption): void {
    setLeaving(client);
    console.info("[client_choice] apply", client.id);
    // A full page load: nothing from this mount runs after the switch.
    leaveTo(`${pathname}?client=${encodeURIComponent(client.id)}`);
  }

  const chosen = choice.kind === "chosen" ? choice.client : null;
  const clients = clientsOf(choice);
  const showPicker = choice.kind !== "list_failed" && choice.kind !== "none";

  return (
    <div className="flex flex-col gap-6" data-mounted-at={mountedAt}>
      {header(chosen)}
      {showPicker ? (
        <AdminClientPicker
          // Remounted when the shown client or the state changes, so the
          // select starts from the current client (or the placeholder).
          // Prefixed: the body below is keyed by the same client, and the
          // two are siblings, so bare ids would collide (two children with
          // one key). Each still re-mounts when the client changes.
          key={`picker-${chosen?.id ?? choice.kind}`}
          clients={clients}
          current={chosen}
          disabled={leaving !== null || bodyBusy || choice.kind === "loading"}
          onApply={apply}
        />
      ) : null}
      {leaving !== null ? (
        <p className="text-sm text-ink-secondary" role="status">
          {CLIENT_LINES.leaving(leaving.label)}
        </p>
      ) : (
        <StateLine
          choice={choice}
          noClient={noClient}
          loadingText={loadingText}
        />
      )}
      {chosen !== null ? (
        <React.Fragment key={`body-${chosen.id}`}>
          {children({
            client: chosen,
            leaving: leaving !== null,
            onBusyChange,
          })}
        </React.Fragment>
      ) : null}
    </div>
  );
}

function StateLine({
  choice,
  noClient,
  loadingText,
}: {
  choice: ClientChoice;
  noClient: ReactNode;
  loadingText: string;
}): JSX.Element | null {
  switch (choice.kind) {
    case "loading":
      return <p className="text-sm text-ink-secondary">{loadingText}</p>;
    case "list_failed":
      return (
        <p className="text-sm text-status-danger-fg" role="alert">
          {CLIENT_LINES.listFailed}
        </p>
      );
    case "none":
      return <p className="text-sm text-ink-secondary">No clients yet</p>;
    case "unchosen":
      return <>{noClient}</>;
    case "stale":
      return (
        <p className="text-sm text-status-warning-fg" role="status">
          {CLIENT_LINES.stale}
        </p>
      );
    case "cookie_failed":
      return (
        <p className="text-sm text-status-danger-fg" role="alert">
          {CLIENT_LINES.cookieFailed}
        </p>
      );
    case "link_unlisted":
      return (
        <p className="text-sm text-status-warning-fg" role="status">
          {CLIENT_LINES.linkUnlisted}
        </p>
      );
    case "link_empty":
      return (
        <p className="text-sm text-status-warning-fg" role="status">
          {CLIENT_LINES.linkEmpty}
        </p>
      );
    case "chosen":
      return null;
  }
}
