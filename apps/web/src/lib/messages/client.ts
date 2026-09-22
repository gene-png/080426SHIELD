"use client";

import { clientFacingError } from "@/lib/describe-save-error";

export interface MessageRow {
  id: string;
  service_id: string;
  author_user_id: string | null;
  author_role: string | null;
  body: string;
  created_at: string;
  read_at: string | null;
}

export interface MessageList {
  messages: MessageRow[];
}

export interface InboxThread {
  service_id: string;
  service_title: string;
  service_kind: string;
  total: number;
  unread: number;
  last_preview: string | null;
  last_at: string | null;
}

export interface InboxResponse {
  threads: InboxThread[];
  unread_total: number;
}

export class MessagesProxyError extends Error {
  constructor(
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(`Messages proxy ${status}`);
  }
}

async function jsonRequest<T>(
  url: string,
  init: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T> {
  const res = await fetch(url, {
    method: init.method ?? "GET",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...(init.body !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (!res.ok) {
    // Read the body ONCE, then try to parse it. Calling res.json() and then
    // res.text() on failure throws "body stream already read", which masked a
    // real 404 behind a confusing error while this path was unwired (issue 4).
    const raw = await res.text();
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
    throw new MessagesProxyError(res.status, payload);
  }
  return (await res.json()) as T;
}

export async function fetchMessages(serviceId: string): Promise<MessageList> {
  return jsonRequest<MessageList>(`/api/proxy/services/${serviceId}/messages`);
}

export async function postMessage(
  serviceId: string,
  body: string,
): Promise<MessageRow> {
  return jsonRequest<MessageRow>(`/api/proxy/services/${serviceId}/messages`, {
    method: "POST",
    body: { body },
  });
}

export async function fetchInbox(): Promise<InboxResponse> {
  return jsonRequest<InboxResponse>("/api/proxy/messages/inbox");
}

export function describeMessagesError(err: unknown): string {
  // CLIENT-FACING. `MessageThread` renders this on
  // `app/self-assessment/[serviceId]/page.tsx`, so a client messaging their
  // consultant reads whatever comes back.
  //
  // It used to end `err instanceof Error ? err.message : "Request failed."`,
  // and `MessagesProxyError` is `super(\`Messages proxy ${status}\`)` -- so a
  // non-proxy throw put "Messages proxy 500" in front of a client. Its proxy
  // branch also fell back to a bare `Request failed (<status>).`, an HTTP
  // status code as client copy, which core principle 2 forbids for the same
  // reason (#318).
  //
  // `clientFacingError` reads the same three payload shapes this hand-rolled
  // chain did -- enveloped `error.message`, string `detail`, and the ARRAY
  // `detail` form this one could not handle at all -- so this is strictly
  // more coverage, not a swap.
  return clientFacingError(err, "We couldn't load your messages just now.");
}
