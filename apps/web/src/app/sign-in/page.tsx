import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, type JSX } from "react";

import { KeycloakSignInButton } from "@/components/auth/KeycloakSignInButton";
import { SignInForm } from "@/components/auth/SignInForm";
import { PublicHeader } from "@/components/site/PublicHeader";
import { isOidcEnabled } from "@/lib/auth/oidc";

export const metadata: Metadata = {
  title: "Sign in",
};

export default async function SignInPage(props: {
  searchParams?: Promise<{ reason?: string }>;
}): Promise<JSX.Element> {
  const searchParams = await props.searchParams;
  const sessionExpired = searchParams?.reason === "session_expired";
  const oidcExchangeFailed = searchParams?.reason === "oidc_exchange_failed";
  // Flag OFF (default): the provider does not exist, so the button is absent and
  // this whole branch collapses — the page is byte-identical to before T6.
  const oidcEnabled = isOidcEnabled();
  return (
    <>
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 py-16">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold text-ink-primary">Sign in</h1>
          <p className="text-sm text-ink-secondary">
            Use the email and password you registered with. If you&apos;ve
            enabled two-factor authentication, we&apos;ll ask for your
            authenticator code next.
          </p>
        </header>
        {sessionExpired ? (
          <div
            role="status"
            className="rounded-md border border-status-warning-border bg-status-warning-bg px-3 py-2 text-sm text-status-warning-fg"
          >
            For your security, your session ended and you&apos;ll need to sign
            in again.
          </div>
        ) : null}
        {oidcExchangeFailed ? (
          <div
            role="alert"
            className="rounded-md border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger-fg"
          >
            We couldn&apos;t sign you in with single sign-on. Your identity was
            verified, but no matching SHIELD account is active for it. Contact
            your administrator, or sign in with your email and password below.
          </div>
        ) : null}
        <Suspense
          fallback={
            <div aria-busy="true" className="text-sm text-ink-tertiary">
              Loading…
            </div>
          }
        >
          <SignInForm />
        </Suspense>
        {oidcEnabled ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3 text-xs text-ink-tertiary">
              <span className="h-px flex-1 bg-border" />
              or
              <span className="h-px flex-1 bg-border" />
            </div>
            <KeycloakSignInButton />
          </div>
        ) : null}
        <p className="text-sm text-ink-secondary">
          New here?{" "}
          <Link
            href="/sign-up"
            className="font-medium text-brand-500 hover:text-brand-600"
          >
            Create an account
          </Link>
        </p>
        <p className="text-sm text-ink-secondary">
          Forgot your password?{" "}
          <Link
            href="/forgot-password"
            className="font-medium text-brand-500 hover:text-brand-600"
          >
            Reset it
          </Link>
        </p>
      </main>
    </>
  );
}
