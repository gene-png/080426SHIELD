"use client";
import * as React from "react";

import { orgDisplayName } from "@/lib/org-name";

import { readActiveClient, readClientList } from "./client-reads";

/**
 * RR-2 (for #1121): which client the Risk Register, Deliverables and Messages
 * pages show. Design note §3.1 and §3.1a.
 *
 * The page DERIVES its client on every render from three things: the URL's
 * `?client=` (read live), and the client list and saved-client cookie (read
 * once, at mount). Nothing about the choice is held in state, so nothing has
 * to be kept in step with the URL.
 */

/** A read's outcome. A pending read is never mapped to `[]` or `null`. */
export type ReadState =
  { state: "pending" } | { state: "ok"; value: unknown } | { state: "failed" };

export interface ClientOption {
  id: string;
  /** The option's own text: `dba_name (legal)` or `orgDisplayName(legal)`. */
  label: string;
}

export interface UrlClient {
  /** `?client` is in the URL at all, even empty or bare. */
  present: boolean;
  value: string | null;
}

export type ClientChoice =
  /** `clients` is the list once it has loaded, while the cookie is pending. */
  | { kind: "loading"; clients: ClientOption[] | null }
  | { kind: "list_failed" }
  | { kind: "none" }
  | { kind: "chosen"; client: ClientOption; clients: ClientOption[] }
  | { kind: "link_unlisted"; clients: ClientOption[] }
  | { kind: "link_empty"; clients: ClientOption[] }
  | { kind: "cookie_failed"; clients: ClientOption[] }
  | { kind: "stale"; clients: ClientOption[] }
  | { kind: "unchosen"; clients: ClientOption[] };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * The list as `AdminClientListResponse` (`{clients: [...]}`). A body without
 * a `clients` array, or with a row that has no string id, is a failed read:
 * fail closed, never "no clients".
 */
function parseList(value: unknown): ClientOption[] | null {
  if (!isRecord(value) || !Array.isArray(value.clients)) return null;
  const out: ClientOption[] = [];
  for (const row of value.clients) {
    if (!isRecord(row) || typeof row.id !== "string" || !row.id) return null;
    const legal = typeof row.legal_name === "string" ? row.legal_name : null;
    const dba = typeof row.dba_name === "string" ? row.dba_name : null;
    out.push({
      id: row.id,
      label: dba ? `${dba} (${orgDisplayName(legal)})` : orgDisplayName(legal),
    });
  }
  return out;
}

/**
 * The cookie body, `{active: string | null}`. Anything else, including a 200
 * with `active` missing, is a failed read (row 6): silence about the cookie is
 * not "no cookie". `undefined` here means unreadable.
 */
function parseActive(value: unknown): string | null | undefined {
  if (!isRecord(value) || !("active" in value)) return undefined;
  const a = value.active;
  if (a === null) return null;
  return typeof a === "string" ? a : undefined;
}

/**
 * §3.1a. The FIRST row that matches; a row whose read is still pending is
 * `loading`. Pure, so every row is a table test.
 */
export function resolveClientChoice(
  list: ReadState,
  cookie: ReadState,
  url: UrlClient,
): ClientChoice {
  // Row 0 (list half): nothing can be decided without the list.
  if (list.state === "pending") return { kind: "loading", clients: null };
  // Row 1.
  const clients = list.state === "ok" ? parseList(list.value) : null;
  if (clients === null) return { kind: "list_failed" };
  // Row 2.
  if (clients.length === 0) {
    if (cookie.state === "failed")
      console.warn("[client_choice] cookie_read_failed (no clients to choose)");
    return { kind: "none" };
  }
  // Rows 3, 4a, 4b: the URL is the admin's choice (Q-R4). A PRESENT parameter
  // never falls back to the cookie or the one-client rule.
  if (url.present) {
    if (!url.value) return { kind: "link_empty", clients };
    const named = clients.find((c) => c.id === url.value);
    return named
      ? { kind: "chosen", client: named, clients }
      : { kind: "link_unlisted", clients };
  }
  // Row 5: the only possible choice. A failed or stale cookie changes nothing.
  if (clients.length === 1)
    return { kind: "chosen", client: clients[0], clients };
  // Row 0 (cookie half).
  if (cookie.state === "pending") return { kind: "loading", clients };
  // Row 6.
  const active = cookie.state === "ok" ? parseActive(cookie.value) : undefined;
  if (active === undefined) return { kind: "cookie_failed", clients };
  // Row 9.
  if (active === null) return { kind: "unchosen", clients };
  // Rows 7 and 8.
  const saved = clients.find((c) => c.id === active);
  return saved
    ? { kind: "chosen", client: saved, clients }
    : { kind: "stale", clients };
}

function settle(
  read: () => Promise<unknown>,
  set: (s: ReadState) => void,
  name: string,
  isActive: () => boolean,
): void {
  read().then(
    (value) => {
      if (isActive()) set({ state: "ok", value });
    },
    (err: unknown) => {
      const e = err as { kind?: unknown; status?: unknown };
      console.error(
        `[client_choice] ${name} read failed`,
        e?.kind ?? null,
        e?.status ?? null,
        err,
      );
      if (isActive()) set({ state: "failed" });
    },
  );
}

/**
 * The two mount-time reads, started once, in parallel. Lives in the
 * component ABOVE the re-keyed body, so a re-key cannot rerun them.
 */
export function useClientReads(): { list: ReadState; cookie: ReadState } {
  const [list, setList] = React.useState<ReadState>({ state: "pending" });
  const [cookie, setCookie] = React.useState<ReadState>({ state: "pending" });
  React.useEffect(() => {
    let active = true;
    const isActive = () => active;
    settle(readClientList, setList, "client list", isActive);
    settle(readActiveClient, setCookie, "active client", isActive);
    return () => {
      active = false;
    };
  }, []);
  return { list, cookie };
}
