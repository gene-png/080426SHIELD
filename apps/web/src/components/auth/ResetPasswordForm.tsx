"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import type { JSX } from "react";

/**
 * Set-a-new-password form (Sprint 6 T5, D-028). The single-use reset token comes
 * from the ?token= query param of the emailed link. On success the user is sent
 * to sign in with the new password.
 */
export function ResetPasswordForm(): JSX.Element {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [done, setDone] = React.useState(false);

  if (!token) {
    return (
      <div
        role="alert"
        className="rounded-md border border-status-danger-border bg-status-danger-bg px-4 py-3 text-sm text-status-danger-fg"
      >
        This reset link is missing its token. Request a new one from{" "}
        <Link href="/forgot-password" className="font-medium underline">
          forgot password
        </Link>
        .
      </div>
    );
  }

  if (done) {
    return (
      <div
        role="status"
        className="rounded-md border border-border bg-surface-card px-4 py-3 text-sm text-ink-secondary"
      >
        Your password has been reset.{" "}
        <Link
          href="/sign-in"
          className="font-medium text-brand-500 hover:text-brand-600"
        >
          Sign in
        </Link>{" "}
        with your new password.
      </div>
    );
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setPending(true);
    setError(null);
    const res = await fetch("/api/proxy/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    });
    if (res.ok) {
      setDone(true);
      setPending(false);
      return;
    }
    const body = (await res.json().catch(() => ({}))) as {
      error?: { reason?: string; message?: string };
    };
    if (body.error?.reason === "password_policy") {
      setError(body.error.message ?? "Choose a stronger password.");
    } else if (body.error?.reason === "invalid_token") {
      setError(
        "This reset link is invalid or has expired. Request a new one from forgot password.",
      );
    } else {
      setError("Something went wrong resetting your password. Try again.");
    }
    setPending(false);
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="password"
          className="text-sm font-medium text-ink-primary"
        >
          New password
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={12}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={error ? "true" : undefined}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden"
        />
        <p className="text-xs text-ink-tertiary">12+ characters.</p>
      </div>
      {error ? (
        <div
          role="alert"
          className="rounded-md border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger-fg"
        >
          {error}
        </div>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}
