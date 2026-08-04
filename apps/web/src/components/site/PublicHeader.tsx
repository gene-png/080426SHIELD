import Link from "next/link";

import { auth } from "@/lib/auth/options";
import { ClientSwitcher } from "@/components/site/ClientSwitcher";
import { SignOutButton } from "@/components/site/SignOutButton";

import type { JSX } from "react";

export async function PublicHeader(): Promise<JSX.Element> {
  const session = await auth();
  const role = session?.role;

  return (
    <header className="border-b border-border-subtle bg-surface-card">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex flex-col leading-tight">
          <span className="text-lg font-semibold tracking-tight text-ink-primary">
            SHIELD
          </span>
          <span className="text-xs font-medium uppercase tracking-wider text-ink-tertiary">
            by Kentro
          </span>
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-4 text-sm">
          {session ? (
            <>
              {role === "client" ? (
                <Link
                  href="/home"
                  className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
                >
                  Home
                </Link>
              ) : null}
              <Link
                href="/assessments"
                className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
              >
                My Assessments
              </Link>
              {role === "client" ? (
                <Link
                  href="/documents"
                  className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
                >
                  Documents
                </Link>
              ) : null}
              <Link
                href="/messages"
                className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
              >
                Messages
              </Link>
              <Link
                href="/account"
                className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
              >
                Account
              </Link>
              {role === "admin" ? (
                <Link
                  href="/admin/queue"
                  className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
                >
                  Admin
                </Link>
              ) : null}
              {role === "admin" ? <ClientSwitcher /> : null}
              <SignOutButton />
            </>
          ) : (
            <>
              <Link
                href="/sign-in"
                className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
              >
                Sign in
              </Link>
              <Link
                href="/sign-up"
                className="rounded-md bg-brand-500 px-3 py-2 font-semibold text-ink-on-accent hover:bg-brand-600"
              >
                Get started
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
