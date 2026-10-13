"use client";
import * as React from "react";

import type { ClientOption } from "@/lib/admin/client-choice";

import type { JSX } from "react";

/**
 * RR-2 (for #1121), design note §3.3: the client picker on the Risk Register,
 * Deliverables and Messages pages.
 *
 * Choosing has an explicit Apply ("Show this client"), never change-on-select:
 * in Chromium, arrow keys on a closed `<select>` fire `change`, which would
 * switch client one keypress at a time.
 *
 * The select shows the placeholder in every state but `chosen`, whatever the
 * list's length, so choosing any client enables Apply, and each state's line
 * ("then select Show this client") names a control that works (D-076).
 */
export function AdminClientPicker({
  clients,
  current,
  disabled,
  onApply,
}: {
  /** null while the list is still loading. */
  clients: ClientOption[] | null;
  /** The client shown now, in `chosen` only. */
  current: ClientOption | null;
  /** Work in flight, a pending load, or Apply already pressed. */
  disabled: boolean;
  onApply: (client: ClientOption) => void;
}): JSX.Element {
  const [selected, setSelected] = React.useState<string>(current?.id ?? "");
  const pick = clients?.find((c) => c.id === selected) ?? null;
  const applyDisabled =
    disabled || clients === null || pick === null || pick.id === current?.id;

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <label className="flex items-center gap-2">
        <span className="text-ink-tertiary">Client</span>
        <select
          aria-label="Client for this page"
          value={selected}
          disabled={disabled || clients === null}
          onChange={(ev) => setSelected(ev.target.value)}
          className="rounded-md border border-border-subtle bg-surface-card px-2 py-1 text-ink-primary"
        >
          <option value="">— pick one —</option>
          {(clients ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={applyDisabled}
        onClick={() => {
          if (pick) onApply(pick);
        }}
        className="rounded-md border border-border px-3 py-1 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:opacity-50"
      >
        Show this client
      </button>
    </div>
  );
}
