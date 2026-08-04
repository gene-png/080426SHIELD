import type { Metadata } from "next";
import Link from "next/link";

import { PublicFooter } from "@/components/site/PublicFooter";
import { PublicHeader } from "@/components/site/PublicHeader";

import type { JSX } from "react";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound(): JSX.Element {
  return (
    <>
      <PublicHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className="mx-auto flex max-w-3xl flex-col px-6 py-24 outline-hidden"
      >
        <p className="text-sm font-semibold uppercase tracking-wider text-ink-tertiary">
          Error 404
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-ink-primary">
          Page not found
        </h1>
        <p className="mt-4 max-w-prose text-ink-secondary">
          The page you are looking for does not exist, has moved, or is not
          available to your account. Use one of the links below to get back on
          track.
        </p>
        <nav
          aria-label="Recovery links"
          className="mt-8 flex flex-wrap items-center gap-4 text-sm"
        >
          <Link
            href="/"
            className="rounded-md bg-brand-500 px-4 py-2 font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Home
          </Link>
          <Link
            href="/assessments"
            className="rounded-md px-4 py-2 font-medium text-ink-secondary hover:text-ink-primary"
          >
            My Assessments
          </Link>
          <Link
            href="/sign-in"
            className="rounded-md px-4 py-2 font-medium text-ink-secondary hover:text-ink-primary"
          >
            Sign in
          </Link>
        </nav>
      </main>
      <PublicFooter />
    </>
  );
}
