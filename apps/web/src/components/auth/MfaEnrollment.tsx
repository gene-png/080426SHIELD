"use client";

import * as React from "react";

import type { JSX } from "react";

interface EnrollResponse {
  secret: string;
  otpauth_uri: string;
}

interface VerifyResponse {
  mfa_enrolled: boolean;
  recovery_codes: string[];
}

type Phase = "idle" | "enrolling" | "verifying" | "done";

/**
 * Account-page TOTP MFA enrollment (Sprint 6 T4, D-027).
 *
 * Three visible states: not enrolled (Enable button) → provisioning shown
 * (secret + otpauth URI + code field) → confirmed (recovery codes shown once).
 * All API traffic flows through the server-side proxy under /api/proxy/auth/mfa.
 */
export function MfaEnrollment({
  initiallyEnrolled,
}: {
  initiallyEnrolled: boolean;
}): JSX.Element {
  const [enrolled, setEnrolled] = React.useState(initiallyEnrolled);
  const [phase, setPhase] = React.useState<Phase>("idle");
  const [secret, setSecret] = React.useState<string | null>(null);
  const [otpauthUri, setOtpauthUri] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [recoveryCodes, setRecoveryCodes] = React.useState<string[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  async function beginEnroll(): Promise<void> {
    setError(null);
    setPhase("enrolling");
    try {
      const res = await fetch("/api/proxy/auth/mfa/enroll", { method: "POST" });
      if (!res.ok) {
        setError("Could not start enrollment. Please try again.");
        setPhase("idle");
        return;
      }
      const data = (await res.json()) as EnrollResponse;
      setSecret(data.secret);
      setOtpauthUri(data.otpauth_uri);
    } catch {
      setError("Something went wrong. Please try again.");
      setPhase("idle");
    }
  }

  async function confirmCode(
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> {
    e.preventDefault();
    setError(null);
    setPhase("verifying");
    try {
      const res = await fetch("/api/proxy/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!res.ok) {
        setError("That code is incorrect or has expired. Try again.");
        setPhase("enrolling");
        return;
      }
      const data = (await res.json()) as VerifyResponse;
      setRecoveryCodes(data.recovery_codes);
      setEnrolled(true);
      setPhase("done");
    } catch {
      setError("Something went wrong. Please try again.");
      setPhase("enrolling");
    }
  }

  if (enrolled && phase !== "done") {
    return (
      <p className="text-sm text-ink-secondary">
        Two-factor authentication is{" "}
        <span className="font-medium text-status-success-fg">enabled</span> on
        your account. You&apos;ll be asked for an authenticator code each time
        you sign in.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {phase === "idle" ? (
        <>
          <p className="text-sm text-ink-secondary">
            Add a second factor to your account. You&apos;ll scan a code into an
            authenticator app (or enter the secret manually), then confirm a
            one-time code.
          </p>
          <button
            type="button"
            onClick={beginEnroll}
            className="self-start rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Enable two-factor authentication
          </button>
        </>
      ) : null}

      {(phase === "enrolling" || phase === "verifying") && secret ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-secondary">
            In your authenticator app, add an account using this setup key, then
            enter the 6-digit code it shows.
          </p>
          <div className="rounded-md border border-border bg-surface-muted px-3 py-2">
            <span className="text-xs font-medium text-ink-tertiary">
              Setup key
            </span>
            <code className="block break-all font-mono text-sm text-ink-primary">
              {secret}
            </code>
          </div>
          {otpauthUri ? (
            <p className="break-all text-xs text-ink-tertiary">
              Provisioning URI: <code>{otpauthUri}</code>
            </p>
          ) : null}
          <form className="flex flex-col gap-2" onSubmit={confirmCode}>
            <label
              htmlFor="mfa-code"
              className="text-sm font-medium text-ink-primary"
            >
              Authenticator code
            </label>
            <input
              id="mfa-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(ev) => setCode(ev.target.value)}
              className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden"
              placeholder="123456"
            />
            <button
              type="submit"
              disabled={phase === "verifying"}
              className="self-start rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {phase === "verifying" ? "Verifying…" : "Confirm"}
            </button>
          </form>
        </div>
      ) : null}

      {phase === "done" ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-status-success-fg">
            Two-factor authentication is now enabled.
          </p>
          <div
            role="alert"
            className="rounded-md border border-status-warning-border bg-status-warning-bg px-3 py-3"
          >
            <p className="text-sm font-medium text-status-warning-fg">
              Save your recovery codes now — they are shown only once.
            </p>
            <p className="mt-1 text-xs text-status-warning-fg">
              Each code can be used once if you lose access to your
              authenticator.
            </p>
            <ul className="mt-2 grid grid-cols-2 gap-1 font-mono text-sm text-ink-primary">
              {recoveryCodes.map((rc) => (
                <li key={rc}>{rc}</li>
              ))}
            </ul>
          </div>
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
    </div>
  );
}
