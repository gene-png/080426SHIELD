"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import type { JSX } from "react";

type Status = "verifying" | "success" | "error" | "missing";

/**
 * Email-verification landing (Sprint 6 T5, D-028). Reads the single-use token
 * from ?token=, submits it once on mount, and shows the outcome. On failure it
 * offers a resend form (enumeration-safe — uniform response).
 */
export function VerifyEmailClient(): JSX.Element {
  const token = useSearchParams().get("token") ?? "";
  const [status, setStatus] = React.useState<Status>(
    token ? "verifying" : "missing",
  );

  React.useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await fetch("/api/proxy/auth/verify-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (cancelled) {
        return;
      }
      setStatus(res.ok ? "success" : "error");
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "verifying") {
    return (
      <p role="status" className="text-sm text-ink-secondary">
        Confirming your email address…
      </p>
    );
  }

  if (status === "success") {
    return (
      <div
        role="status"
        className="rounded-md border border-border bg-surface-card px-4 py-3 text-sm text-ink-secondary"
      >
        Your email address is confirmed.{" "}
        <Link
          href="/sign-in"
          className="font-medium text-brand-500 hover:text-brand-600"
        >
          Sign in
        </Link>{" "}
        to continue.
      </div>
    );
  }

  // "error" or "missing": the link is invalid/expired/absent — offer a resend.
  return (
    <div className="flex flex-col gap-4">
      <div
        role="alert"
        className="rounded-md border border-status-danger-border bg-status-danger-bg px-4 py-3 text-sm text-status-danger-fg"
      >
        {status === "missing"
          ? "This verification link is missing its token."
          : "This verification link is invalid or has expired."}{" "}
        Request a new one below.
      </div>
      <ResendVerification />
    </div>
  );
}

function ResendVerification(): JSX.Element {
  const [email, setEmail] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [message, setMessage] = React.useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setPending(true);
    setMessage(null);
    const res = await fetch("/api/proxy/auth/resend-verification", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const body = (await res.json().catch(() => ({}))) as { message?: string };
    setMessage(
      body.message ??
        "If an account matches that email, we've sent a new confirmation link.",
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
    <form className="flex flex-col gap-3" onSubmit={onSubmit} noValidate>
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
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Sending…" : "Resend confirmation"}
      </button>
    </form>
  );
}
