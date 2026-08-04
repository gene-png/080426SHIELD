"use client";
import * as React from "react";

import type { JSX } from "react";

/**
 * Password-reset request form (Sprint 6 T5, D-028). Enumeration-safe: the
 * backend returns the same uniform message whether or not the account exists,
 * and this form shows exactly that message — it never confirms an account.
 */
export function ForgotPasswordForm(): JSX.Element {
  const [email, setEmail] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setPending(true);
    setMessage(null);
    const res = await fetch("/api/proxy/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const body = (await res.json().catch(() => ({}))) as { message?: string };
    setMessage(
      body.message ??
        "If an account matches that email, we've sent a message with next steps.",
    );
    setPending(false);
  }

  if (message) {
    return (
      <div
        role="status"
        className="rounded-md border border-border bg-surface-card px-4 py-3 text-sm text-ink-secondary"
      >
        {message}
      </div>
    );
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-sm font-medium text-ink-primary">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden"
          placeholder="you@example.gov"
        />
      </div>
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Sending…" : "Send reset link"}
      </button>
    </form>
  );
}
