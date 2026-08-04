import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as messagesClient from "@/lib/messages/client";

import { MessageThread } from "./MessageThread";

// Deterministic + offline: the lib client is fully mocked, so no fetch, no
// network, no timers. Each test drives the exact resolution ordering that the
// reqSeq stale-fetch guard exists to defend against.
vi.mock("@/lib/messages/client", () => ({
  fetchMessages: vi.fn(),
  postMessage: vi.fn(),
  describeMessagesError: vi.fn((err: unknown) =>
    err instanceof Error ? err.message : "Request failed.",
  ),
}));

const fetchMessages = vi.mocked(messagesClient.fetchMessages);
const postMessage = vi.mocked(messagesClient.postMessage);

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (err: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function msg(
  overrides: Partial<messagesClient.MessageRow>,
): messagesClient.MessageRow {
  return {
    id: "id",
    service_id: "svc",
    author_user_id: null,
    author_role: "admin",
    body: "body",
    created_at: "2026-07-10T00:00:00Z",
    read_at: null,
    ...overrides,
  };
}

describe("MessageThread reqSeq stale-fetch guard", () => {
  it("discards a stale mount GET that resolves after a newer send", async () => {
    // Mount load is deliberately slow: it stays in-flight while the user sends.
    const load = deferred<messagesClient.MessageList>();
    fetchMessages.mockReturnValue(load.promise);
    const sent = msg({
      id: "sent-1",
      body: "just sent",
      author_role: "client",
    });
    postMessage.mockResolvedValue(sent);

    render(<MessageThread serviceId="svc-1" />);

    // The composer is available even while the initial load is pending.
    fireEvent.change(screen.getByPlaceholderText("Write a message…"), {
      target: { value: "just sent" },
    });

    // Send: optimistic append bumps reqSeq, invalidating the in-flight GET.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    });

    // Now the slow mount GET resolves with OLD server rows. Without the guard,
    // this setMessages(old) would clobber the just-sent message.
    await act(async () => {
      load.resolve({ messages: [msg({ id: "stale-1", body: "stale row" })] });
    });

    expect(screen.getByText("just sent")).toBeInTheDocument();
    expect(screen.queryByText("stale row")).not.toBeInTheDocument();
  });

  it("surfaces a failed initial load to the error state (fail loudly)", async () => {
    fetchMessages.mockRejectedValue(new Error("boom-network"));

    render(<MessageThread serviceId="svc-err" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("boom-network");
  });
});
