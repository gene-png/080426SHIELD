import type { Metadata } from "next";
import Link from "next/link";

import { SignUpForm } from "@/components/auth/SignUpForm";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Create your SHIELD account",
};

export default function SignUpPage(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 py-16">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold text-ink-primary">
            Create your account
          </h1>
          <p className="text-sm text-ink-secondary">
            Sign up with any email and we&apos;ll set up your organization
            automatically. Coworkers who register with the same company email
            domain join the same workspace; personal email addresses each get
            their own private workspace.
          </p>
        </header>
        <SignUpForm />
        <p className="text-sm text-ink-secondary">
          Already have an account?{" "}
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
