"use client";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import * as React from "react";

import type { JSX } from "react";

interface FieldErrors {
  email?: string;
  password?: string;
  display_name?: string;
  form?: string;
}

export function SignUpForm(): JSX.Element {
  const router = useRouter();
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [displayName, setDisplayName] = React.useState("");
  const [errors, setErrors] = React.useState<FieldErrors>({});
  const [pending, setPending] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setErrors({});
    setPending(true);

    const res = await fetch("/api/proxy/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, display_name: displayName }),
    });
    if (res.status === 409 || res.status === 422) {
      // The API returns a typed error envelope: error.reason is a stable
      // machine code, error.message is human-friendly copy. Map each reason to
      // the field it belongs to so the copy lands next to the offending input
      // (and never surfaces a raw "Request validation failed.").
      const body = (await res.json()) as {
        error?: { message?: string; reason?: string };
      };
      const reason = body.error?.reason;
      const message = body.error?.message;
      if (reason === "email_exists") {
        setErrors({
          email: "An account already exists for that email. Sign in instead.",
        });
      } else if (reason === "password_policy") {
        setErrors({ password: message ?? "Choose a stronger password." });
      } else if (reason && message) {
        // Any other typed backend rejection (D-016 envelope) — e.g. the rare
        // email_domain_unavailable or email_invalid — carries friendly copy, so
        // surface it on the email field. (Self-registration is open now, so the
        // old domain-approval reasons no longer fire on the happy path.)
        setErrors({ email: message });
      } else {
        // Raw schema validation (RequestValidationError) carries no typed
        // reason and its message is the unfriendly "Request validation failed."
        // Show a plain-language prompt instead of leaking that string.
        setErrors({
          form: "Please double-check your name, email, and password (12+ characters), then try again.",
        });
      }
      setPending(false);
      return;
    }
    if (!res.ok) {
      setErrors({
        form: "Something went wrong creating your account. Try again.",
      });
      setPending(false);
      return;
    }

    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    if (!result || result.error) {
      router.replace("/sign-in?registered=1");
      return;
    }
    // Full-page navigation so the server re-renders the header/nav with the new
    // session and the client lands on the intake form without a manual refresh.
    window.location.assign("/intake");
  }

  return (
    <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="display_name"
          className="text-sm font-medium text-ink-primary"
        >
          Full name
        </label>
        <input
          id="display_name"
          type="text"
          required
          value={displayName}
          autoComplete="name"
          onChange={(e) => setDisplayName(e.target.value)}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden"
        />
      </div>
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
          aria-invalid={errors.email ? "true" : undefined}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary placeholder:text-ink-tertiary focus:border-border-focus focus:outline-hidden"
          placeholder="you@example.gov"
        />
        {errors.email ? (
          <p className="text-xs text-status-danger-fg">{errors.email}</p>
        ) : null}
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
          required
          minLength={12}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={errors.password ? "true" : undefined}
          className="rounded-md border border-border bg-surface-card px-3 py-2 text-sm text-ink-primary focus:border-border-focus focus:outline-hidden"
        />
        <p className="text-xs text-ink-tertiary">
          12+ characters. Choose something memorable.
        </p>
        {errors.password ? (
          <p className="text-xs text-status-danger-fg">{errors.password}</p>
        ) : null}
      </div>
      {errors.form ? (
        <div
          role="alert"
          className="rounded-md border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger-fg"
        >
          {errors.form}
        </div>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="rounded-md bg-brand-500 px-4 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? "Creating account…" : "Create account"}
      </button>
    </form>
  );
}
