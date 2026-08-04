"use client";
import * as React from "react";

import { useAiStatus } from "@/lib/admin/aiStatus";
import { removeLlmKey, setLlmKey, type AiStatus } from "@/lib/admin/client";

import type { JSX } from "react";

/**
 * Issue 2: paste, replace, or remove the provider API key (Management page).
 *
 * The key is write-only from the UI's point of view — nothing reads it back,
 * so this shows only whether a key is loaded and where it came from. The
 * masked input exists so the value isn't shoulder-surfable while typing; it is
 * not a security boundary.
 *
 * `onChanged` lets the shell-level banner re-read status immediately, which is
 * what makes the offline warning reappear the first time Run AI is used after
 * a key is removed (see `aiStatusKey` in aiStatus.ts).
 */
export function LlmKeyPanel({
  onChanged,
}: {
  onChanged?: () => void;
}): JSX.Element {
  // Shares the shell banner's loader rather than running a second effect of
  // its own — one place decides how AI status is fetched.
  const { status: loaded, refresh } = useAiStatus();
  // A save/remove returns fresh status; prefer it until the next refresh lands.
  const [override, setOverride] = React.useState<AiStatus | null>(null);
  const status = override ?? loaded;

  const [key, setKey] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [confirmingRemove, setConfirmingRemove] = React.useState(false);

  async function onSave(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!key.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const next = await setLlmKey(key.trim());
      setOverride(next);
      setKey("");
      setNotice(
        next.ready
          ? "Key validated and saved. Live AI is on."
          : "Key saved, but AI still isn't live — see the detail below.",
      );
      onChanged?.();
    } catch (err) {
      // The API validates against the provider before storing, so this message
      // is the provider's own reason (bad key, wrong model, rate limit).
      setError(err instanceof Error ? err.message : "Failed to save the key.");
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(): Promise<void> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await removeLlmKey();
      setConfirmingRemove(false);
      setOverride(null);
      refresh();
      setNotice("Key removed. AI steps will generate offline responses again.");
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to remove the key.",
      );
    } finally {
      setBusy(false);
    }
  }

  const hasStoredKey = status?.key_source === "database";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span
          className={
            "rounded-full px-2 py-0.5 text-xs font-semibold " +
            (status?.ready
              ? "bg-status-success-bg text-status-success-fg"
              : "bg-status-warning-bg text-status-warning-fg")
          }
        >
          {status === null
            ? "Checking…"
            : status.ready
              ? "Live AI on"
              : "Offline"}
        </span>
        {status ? (
          <span className="text-ink-secondary">
            {status.provider} · {status.model} · key:{" "}
            {status.key_source === "none" ? "not loaded" : status.key_source}
          </span>
        ) : null}
      </div>

      {status ? (
        <p className="max-w-prose text-sm text-ink-secondary">
          {status.detail}
        </p>
      ) : null}

      <form onSubmit={(e) => void onSave(e)} className="flex flex-wrap gap-2">
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={
            hasStoredKey ? "Paste a new key to replace" : "Paste API key"
          }
          aria-label="Provider API key"
          autoComplete="off"
          className="min-w-[18rem] flex-1 rounded-md border border-border bg-surface-card px-3 py-2 font-mono text-sm"
        />
        <button
          type="submit"
          disabled={busy || !key.trim()}
          className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Validating…" : hasStoredKey ? "Replace key" : "Save key"}
        </button>
        {hasStoredKey ? (
          confirmingRemove ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void onRemove()}
                disabled={busy}
                className="rounded-md bg-status-danger-fg px-3 py-2 text-xs font-semibold text-ink-on-accent disabled:opacity-60"
              >
                Yes, remove
              </button>
              <button
                type="button"
                onClick={() => setConfirmingRemove(false)}
                className="rounded-md border border-border bg-surface-card px-3 py-2 text-xs font-semibold text-ink-primary hover:bg-surface-sunken"
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmingRemove(true)}
              className="rounded-md border border-status-danger-border px-3 py-2 text-xs font-semibold text-status-danger-fg hover:bg-status-danger-bg"
            >
              Remove key
            </button>
          )
        ) : null}
      </form>

      <p className="text-xs text-ink-tertiary">
        The key is checked against the provider before it is saved, stored
        encrypted, and never shown again. One key serves the whole deployment.
      </p>

      {error ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="text-sm text-status-success-fg">
          {notice}
        </p>
      ) : null}
    </div>
  );
}
