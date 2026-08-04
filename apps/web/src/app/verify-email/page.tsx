import type { Metadata } from "next";
import { Suspense } from "react";

import { VerifyEmailClient } from "@/components/auth/VerifyEmailClient";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Confirm your SHIELD email",
};

export default function VerifyEmailPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 py-16">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold text-ink-primary">
            Confirm your email
          </h1>
        </header>
        {/* useSearchParams needs a Suspense boundary during static render. */}
        <Suspense
          fallback={<p className="text-sm text-ink-secondary">Loading…</p>}
        >
          <VerifyEmailClient />
        </Suspense>
      </main>
    </>
  );
}
