"use client";
import * as React from "react";

import { useAiStatus } from "@/lib/admin/aiStatus";
import {
  fetchAiStatus,
  removeLlmKey,
  setLlmKey,
  type AiStatus,
} from "@/lib/admin/client";

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
/** What removing the stored key actually did, from the status read after it. */
function removalNotice(next: AiStatus | null): string {
  if (next === null) {
    return "Key removed. The AI status could not be re-read — refresh the page to see what AI will do now.";
  }
  if (next.serves === "live") {
    // Not "on the environment key": for vertex it would be ADC. The detail
    // above names what AI is running on.
    return "Key removed. AI is still live.";
  }
  if (next.serves === "offline") {
    return "Key removed. AI steps will generate offline responses again.";
  }
  return "Key removed. Run AI will fail until the cause above is fixed.";
}

export function LlmKeyPanel({
  onChanged,
}: {
  onChanged?: () => void;
}): JSX.Element {
  // Shares the shell banner's loader rather than running a second effect of
  // its own — one place decides how AI status is fetched.
  const { status: loaded, phase, refresh } = useAiStatus();
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
      // #472 round 1: "offline again" was said whatever happened next. In live
      // mode an ENVIRONMENT key takes over and Run-AI keeps calling the
      // provider, so the notice comes from the status read AFTER the removal.
      let next: AiStatus | null = null;
      try {
        next = await fetchAiStatus();
      } catch (err) {
        // Stated, not swallowed: the key IS removed; only the re-read failed.
        console.warn("[llm-key] status re-read after removal failed", err);
      }
      setOverride(next);
      if (next === null) refresh();
      setNotice(removalNotice(next));
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
            ? phase === "error"
              ? "Unknown"
              : "Checking…"
            : status.ready
              ? "Live AI on"
              : status.serves === "broken"
                ? "Not working"
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
      ) : phase === "error" ? (
        <p role="alert" className="max-w-prose text-sm text-status-danger-fg">
          The AI status could not be read, so what Run AI will do is unknown. A
          key pasted here is still checked against the provider before it is
          saved.
        </p>
      ) : null}

      <form onSubmit={(e) => void onSave(e)} className="flex flex-wrap gap-2">
        {/* #472 round 2: the paste form renders only where a key can be
            LOADED here (`can_configure`). For openai and gemini the validator
            refuses a pasted key, and vertex has none -- the form stood under
            server copy saying so. Remove stays: a stored key can always be
            removed, and the build-refusal copy tells the admin to. */}
        {/* A FAILED status read is neither "loading" nor "cannot load a
            key here": offer the form, because the server validates the key
            anyway (round 3 on #472). */}
        {status?.can_configure || (status === null && phase === "error") ? (
          <>
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
          </>
        ) : status ? (
          <p className="text-sm text-ink-secondary">
            A key for {status.provider} cannot be loaded here — see the detail
            above for what this provider needs.
          </p>
        ) : null}
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
