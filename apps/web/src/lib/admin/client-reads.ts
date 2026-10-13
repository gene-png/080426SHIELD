"use client";

/**
 * RR-2 (for #1121), design note §3.1 and §0i finding 4: the two reads the
 * twin admin pages make once, at mount. Each returns the API's body AS
 * RECEIVED. Checking its shape is `resolveClientChoice`'s job, so a 200 whose
 * `active` is neither a string nor null reaches the check that calls it a
 * failed read, instead of being cast away here.
 *
 * Their own module, so a test can mock the reads while the real resolver runs.
 */

/**
 * A read that did not answer 2xx. It carries the facts, and NO copy: nothing
 * renders its message. The page logs `kind` and `status` and shows its own
 * line (§7 strings 8 and 11).
 */
export class ClientReadError extends Error {
  constructor(
    public readonly kind: "client_list" | "active_client",
    public readonly status: number,
  ) {
    super("client read failed");
    this.name = "ClientReadError";
  }
}

async function readJson(
  url: string,
  kind: ClientReadError["kind"],
): Promise<unknown> {
  const res = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new ClientReadError(kind, res.status);
  return (await res.json()) as unknown;
}

/** `GET /api/proxy/admin/clients`: `AdminClientListResponse`, unchecked. */
export function readClientList(): Promise<unknown> {
  return readJson("/api/proxy/admin/clients", "client_list");
}

/** `GET /api/active-client`: `{active: string | null}`, unchecked. */
export function readActiveClient(): Promise<unknown> {
  return readJson("/api/active-client", "active_client");
}
