import type { Metadata } from "next";
import { Suspense } from "react";

import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Choose a new SHIELD password",
};

export default function ResetPasswordPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 py-16">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold text-ink-primary">
            Choose a new password
          </h1>
          <p className="text-sm text-ink-secondary">
            Set a new password for your SHIELD account.
          </p>
        </header>
        {/* useSearchParams needs a Suspense boundary during static render. */}
        <Suspense
          fallback={<p className="text-sm text-ink-secondary">Loading…</p>}
        >
          <ResetPasswordForm />
        </Suspense>
      </main>
    </>
  );
}
