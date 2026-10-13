"use client";
import * as React from "react";
import Link from "next/link";

import { Card, CardBody, EmptyState } from "@shield/design-system";

import {
  ClientScopedPage,
  type ClientScopedBodyProps,
} from "@/components/admin/ClientScopedPage";
import type { ClientOption } from "@/lib/admin/client-choice";
import { workspaceHref } from "@/lib/admin/types";
import { SERVICE_LABELS, type ServiceType } from "@/lib/intake/types";
import {
  describeMessagesError,
  fetchInbox,
  type InboxThread,
} from "@/lib/messages/client";

import type { JSX } from "react";

function fmtTime(value: string | null): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function ThreadRow({ thread }: { thread: InboxThread }): JSX.Element {
  const kind = thread.service_kind as ServiceType;
  const href = workspaceHref(kind, thread.service_id);
  const label = SERVICE_LABELS[kind] ?? thread.service_kind;
  const inner = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-ink-primary">
            {thread.service_title}
          </span>
          {thread.unread > 0 ? (
            <span className="rounded-full bg-brand-500 px-2 py-0.5 text-xs font-semibold text-ink-on-accent">
              {thread.unread} new
            </span>
          ) : null}
        </div>
        <p className="truncate text-sm text-ink-secondary">
          {label} · {thread.last_preview ?? "No messages"}
        </p>
      </div>
      <span className="shrink-0 text-xs text-ink-tertiary">
        {fmtTime(thread.last_at)}
      </span>
    </div>
  );
  return (
    <Card>
      <CardBody>
        {href ? (
          <Link href={href} className="block hover:opacity-80">
            {inner}
          </Link>
        ) : (
          inner
        )}
      </CardBody>
    </Card>
  );
}

/** §7, approved verbatim (#736 6130838759). */
const MESSAGES_NO_CLIENT =
  "Messages are listed per client. Choose a client above, then select Show this client.";
const MESSAGES_SUBTITLE =
  "Threads for the client chosen above, newest first. The badge counts messages you haven't opened yet.";
const MESSAGES_EMPTY =
  "Threads appear here once a service for this client has a conversation.";

/**
 * RR-2 (for #1121), design note §3.5: the h1 and subtitle moved here from the
 * server-rendered page, because they depend on the chosen client. The
 * subtitle shows only in `chosen`: "the client chosen above" is false when
 * none is.
 */
function MessagesHeader({
  chosen,
}: {
  chosen: ClientOption | null;
}): JSX.Element {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-ink-primary">
        {chosen ? `Messages for ${chosen.label}` : "Messages"}
      </h1>
      {chosen ? (
        <p className="mt-1 text-sm text-ink-secondary">{MESSAGES_SUBTITLE}</p>
      ) : null}
    </div>
  );
}

/**
 * RR-2 (for #1121): scoped by the page's own client picker
 * (`ClientScopedPage`), not by the shared active-client cookie.
 */
export function InboxView(): JSX.Element {
  return (
    <ClientScopedPage
      header={(chosen) => <MessagesHeader chosen={chosen} />}
      noClient={
        <EmptyState
          title="Pick a client first"
          description={MESSAGES_NO_CLIENT}
        />
      }
    >
      {(props) => <InboxBody {...props} />}
    </ClientScopedPage>
  );
}

/** Read-only, so there is no work in flight to lock the picker with. */
function InboxBody({ client }: ClientScopedBodyProps): JSX.Element {
  const clientId = client.id;
  const [threads, setThreads] = React.useState<InboxThread[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    fetchInbox(clientId)
      .then((r) => {
        if (active) setThreads(r.threads);
      })
      .catch((err) => {
        if (active) setError(describeMessagesError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [clientId]);

  if (loading) return <p className="text-sm text-ink-tertiary">Loading…</p>;
  if (error)
    return (
      <p className="text-sm text-status-danger-fg" role="alert">
        {error}
      </p>
    );
  if (threads.length === 0)
    return (
      <EmptyState title="No message threads" description={MESSAGES_EMPTY} />
    );

  return (
    <div className="flex flex-col gap-3">
      {threads.map((t) => (
        <ThreadRow key={t.service_id} thread={t} />
      ))}
    </div>
  );
}
