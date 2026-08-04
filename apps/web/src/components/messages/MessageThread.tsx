"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";

import {
  describeMessagesError,
  fetchMessages,
  postMessage,
  type MessageRow,
} from "@/lib/messages/client";

import type { JSX } from "react";

export interface MessageThreadProps {
  serviceId: string;
  /** Heading override; defaults to "Messages". */
  title?: string;
}

function authorLabel(role: string | null): string {
  if (role === "admin") return "SHIELD analyst";
  if (role === "client") return "Client";
  return "Participant";
}

function fmtTime(value: string): string {
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function MessageThread({
  serviceId,
  title = "Messages",
}: MessageThreadProps): JSX.Element {
  const [messages, setMessages] = React.useState<MessageRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [draft, setDraft] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Monotonic request sequence: only the newest messages GET may write state.
  // Without this, a slow mount-time load (StrictMode duplicates, next-dev
  // queuing) resolving AFTER onSend's optimistic append calls setMessages(rows)
  // and clobbers the just-sent message — the T8 stale-fetch race. onSend bumps
  // the sequence when it appends, so any in-flight GET is discarded on arrival.
  const reqSeq = React.useRef(0);

  const load = React.useCallback(async () => {
    const seq = ++reqSeq.current;
    const { messages: rows } = await fetchMessages(serviceId);
    if (seq === reqSeq.current) {
      setMessages(rows);
      console.debug(`[MessageThread] messages applied (seq ${seq})`);
    } else {
      console.debug(
        `[MessageThread] discarded stale messages response (seq ${seq}, latest ${reqSeq.current})`,
      );
    }
  }, [serviceId]);

  React.useEffect(() => {
    (async () => {
      try {
        await load();
      } catch (err) {
        setError(describeMessagesError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [load]);

  async function onSend(): Promise<void> {
    const text = draft.trim();
    if (!text) return;
    setSending(true);
    setError(null);
    try {
      const created = await postMessage(serviceId, text);
      // Invalidate any in-flight mount/reload GET: its late setMessages(rows)
      // would clobber this append and hide the just-sent message (T8 race).
      reqSeq.current += 1;
      setMessages((prev) => [...prev, created]);
      setDraft("");
    } catch (err) {
      setError(describeMessagesError(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          A shared thread for this assessment. Use it to ask for, or provide,
          more information without leaving the workspace.
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        {error ? (
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        ) : null}

        <div className="flex max-h-96 flex-col gap-3 overflow-y-auto">
          {loading ? (
            <p className="text-sm text-ink-tertiary">Loading…</p>
          ) : messages.length === 0 ? (
            <p className="text-sm text-ink-secondary">
              No messages yet. Start the conversation below.
            </p>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className="rounded-lg border border-border-subtle bg-surface-card px-3 py-2"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs font-semibold text-ink-primary">
                    {authorLabel(m.author_role)}
                  </span>
                  <span className="text-xs text-ink-tertiary">
                    {fmtTime(m.created_at)}
                  </span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-sm text-ink-secondary">
                  {m.body}
                </p>
              </div>
            ))
          )}
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor={`msg-${serviceId}`} className="sr-only">
            Write a message
          </label>
          <textarea
            id={`msg-${serviceId}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            placeholder="Write a message…"
            className="w-full rounded-md border border-border-default bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-brand-500 focus:outline-hidden"
          />
          <div>
            <button
              type="button"
              onClick={() => void onSend()}
              disabled={sending || draft.trim().length === 0}
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {sending ? "Sending…" : "Send"}
            </button>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
