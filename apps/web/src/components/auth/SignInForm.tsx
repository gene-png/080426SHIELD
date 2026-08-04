"use client";
import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import type { JSX } from "react";

export function SignInForm(): JSX.Element {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") ?? "/";

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [totp, setTotp] = React.useState("");
  // Once the backend signals MFA is enrolled, reveal the code field and keep it
  // shown for retries.
  const [mfaRequired, setMfaRequired] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const result = await signIn("credentials", {
        email,
        password,
        // Only send `totp` when the user actually entered one. next-auth's
        // client serializes the body with `new URLSearchParams({...})`, which
        // coerces `undefined` to the string "undefined" — a truthy value that
        // defeats authorize's `if (!totp)` guard, so the MFA-required branch
        // would verify a bogus code instead of prompting and the authenticator
        // field would never appear (Sprint 8 T4).
        ...(totp ? { totp } : {}),
        redirect: false,
      });
      if (result?.code === "mfa_required") {
        // Correct password; now collect the authenticator code. In v5 every
        // credentials failure surfaces as error "CredentialsSignin"; the
        // distinguishing signal for the MFA branch is the custom `code`
        // (from the CredentialsSignin subclass thrown in authorize).
        setMfaRequired(true);
        setError(null);
        setPending(false);
        return;
      }
      if (!result || result.error) {
        setError(
          mfaRequired
            ? "That code is incorrect or has expired. Try again."
            : "Invalid email or password.",
        );
        setPending(false);
        return;
      }
      // Full-page navigation (not router.replace) so the server re-renders the
      // header/nav with the new session cookie - a soft nav can serve the
      // cached logged-out tree and leave the nav stale until a manual refresh.
      window.location.assign(callbackUrl);
    } catch {
      setError("Something went wrong. Try again.");
      setPending(false);
    }
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
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden"
          placeholder="you@example.gov"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="password"
          className="text-sm font-medium text-ink-primary"
        >
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          minLength={1}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden"
        />
      </div>
      {mfaRequired ? (
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="totp"
            className="text-sm font-medium text-ink-primary"
          >
            Authenticator code
          </label>
          <input
            id="totp"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            required
            value={totp}
            onChange={(e) => setTotp(e.target.value)}
            className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden"
            placeholder="6-digit code or recovery code"
          />
          <p className="text-xs text-ink-tertiary">
            Enter the code from your authenticator app, or one of your recovery
            codes.
          </p>
        </div>
      ) : null}
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
        {pending ? "Signing in…" : mfaRequired ? "Verify code" : "Sign in"}
      </button>
    </form>
  );
}
