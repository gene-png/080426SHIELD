import Link from "next/link";

import { auth } from "@/lib/auth/options";

import type { JSX } from "react";

export async function Hero(): Promise<JSX.Element> {
  const session = await auth();
  const authed = Boolean(session);
  return (
    <section className="border-b border-border-subtle bg-surface-card">
      <div className="mx-auto max-w-6xl px-6 py-16 sm:py-24">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
          Federal-grade cybersecurity assessments
        </p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ink-primary sm:text-5xl">
          One platform:{" "}
          <span className="text-brand-500">Endless Possibilities</span>
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-ink-secondary">
          SHIELD by Kentro centralizes assessment workflows, evidence
          collection, scoring, reporting, and executive visibility into a single
          secure platform.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            href={authed ? "/intake" : "/sign-up"}
            className="rounded-md bg-brand-500 px-5 py-3 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
          >
            Start an assessment
          </Link>
          {authed ? null : (
            <Link
              href="/sign-in"
              className="rounded-md border border-border bg-surface-card px-5 py-3 text-sm font-semibold text-ink-primary hover:bg-surface-sunken"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
