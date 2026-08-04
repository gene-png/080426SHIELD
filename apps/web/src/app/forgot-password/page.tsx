import type { Metadata } from "next";
import Link from "next/link";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Reset your SHIELD password",
};

export default function ForgotPasswordPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 py-16">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold text-ink-primary">
            Reset your password
          </h1>
          <p className="text-sm text-ink-secondary">
            Enter your email and we&apos;ll send a link to choose a new
            password. For your security we&apos;ll respond the same way whether
            or not an account exists.
          </p>
        </header>
        <ForgotPasswordForm />
        <p className="text-sm text-ink-secondary">
          Remembered it?{" "}
          <Link
            href="/sign-in"
            className="font-medium text-brand-500 hover:text-brand-600"
          >
            Sign in
          </Link>
        </p>
      </main>
    </>
  );
}
