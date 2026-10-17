"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AiStatusBanner } from "@/components/admin/AiStatusBanner";
import { SHELL_COPY } from "@/components/service-shell/shellCopy";
import { SignOutButton } from "@/components/site/SignOutButton";
import { SkipToContent } from "@/components/site/SkipToContent";

import { isClientFramePage } from "./frameWidth";

import type { JSX } from "react";

/**
 * Admin shell (Navigation_Spec §2): a header carrying the signed-in identity,
 * one top bar of admin links at every width, and a skip-to-content link. #1385:
 * the bar replaced the left sidebar, so the left column is free for the
 * CLIENT: a page under a client's frame shows that client's rail as its left
 * column (the frame's own layout renders it), and every other page has none.
 */

interface NavItem {
  label: string;
  href: string;
}

const NAV: NavItem[] = [
  { label: "Intake Queue", href: "/admin/queue" },
  // T6: the client-scoped frame (`/admin/clients/{id}/...`).
  { label: SHELL_COPY.navClients, href: "/admin/clients" },
  { label: "Deliverables", href: "/admin/deliverables" },
  { label: "Messages", href: "/admin/messages" },
  { label: "Audit", href: "/admin/audit" },
  { label: "System Health", href: "/admin/health" },
  { label: "Management", href: "/admin/management" },
];

/**
 * RR-2 (for #1121), design note §3.6: the three pages that share a client
 * picker. Moving between them keeps the chosen client: while the current page
 * is one of them and its URL has `client`, the bar's links to them carry the
 * same value. Risk Register is no longer in the bar (#1385: each client's own
 * list links to its register), but its page is still one of the three, so a
 * link TO Deliverables or Messages from it still carries the client. The shell judges nothing (it reads no client list and never the
 * cookie): an unlisted or empty value is carried as it is, and the next page
 * says so. Every other link, and every link on any other page, is unchanged.
 */
const TWIN_PAGES = new Set([
  "/admin/deliverables",
  "/admin/risk-register",
  "/admin/messages",
]);

export function navHref(
  href: string,
  pathname: string,
  client: string | null,
): string {
  if (client === null || !TWIN_PAGES.has(pathname) || !TWIN_PAGES.has(href))
    return href;
  return `${href}?client=${encodeURIComponent(client)}`;
}

function TopBarLinks({
  pathname,
  client,
}: {
  pathname: string;
  client: string | null;
}): JSX.Element {
  return (
    <>
      {NAV.map((item) => {
        // `aria-current` compares the path alone, which carries no query.
        const active =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={navHref(item.href, pathname, client)}
            aria-current={active ? "page" : undefined}
            className={
              "rounded-md px-3 py-2 text-sm font-medium " +
              (active
                ? "bg-brand-50 text-brand-600"
                : "text-ink-secondary hover:bg-surface-sunken hover:text-ink-primary")
            }
          >
            {item.label}
          </Link>
        );
      })}
    </>
  );
}

/**
 * Reads the URL's `client`. It sits inside a Suspense boundary whose fallback
 * renders the same links with bare hrefs, so the bar never disappears.
 */
function WithClientParam({
  children,
}: {
  children: (client: string | null) => React.ReactNode;
}): JSX.Element {
  const params = useSearchParams();
  return <>{children(params?.get("client") ?? null)}</>;
}

export function AdminShell({
  email,
  children,
}: {
  email?: string | null;
  children: React.ReactNode;
}): JSX.Element {
  const pathname = usePathname();
  const clientFrame = isClientFramePage(pathname);

  return (
    <div className="min-h-screen bg-surface-sunken">
      <SkipToContent />
      <header className="flex items-center justify-between border-b border-border-subtle bg-surface-card px-6 py-3">
        <Link href="/admin/queue" className="flex flex-col leading-tight">
          <span className="text-lg font-semibold tracking-tight text-ink-primary">
            SHIELD
          </span>
          <span className="text-xs font-medium uppercase tracking-wider text-ink-tertiary">
            Admin console
          </span>
        </Link>
        <div className="flex items-center gap-3">
          {email ? (
            <span className="text-xs text-ink-tertiary">{email}</span>
          ) : null}
          <SignOutButton />
        </div>
      </header>
      <nav
        className="flex flex-wrap items-center gap-1 border-b border-border-subtle bg-surface-card px-4 py-2"
        aria-label="Primary"
      >
        <Suspense fallback={<TopBarLinks pathname={pathname} client={null} />}>
          <WithClientParam>
            {(client) => <TopBarLinks pathname={pathname} client={client} />}
          </WithClientParam>
        </Suspense>
      </nav>
      <main
        id="main-content"
        tabIndex={-1}
        className={
          "w-full min-w-0 focus:outline-2 focus:outline-offset-4 focus:outline-brand-500 " +
          // #1385 (Gene's spec): a page with no client uses the full width, so
          // the shell caps nothing; the client frame keeps its own cap.
          (clientFrame ? "" : "px-6 py-8")
        }
      >
        {/* Issue 2: shell-level so the warning is visible on every admin
            page including the landing one, not just one workspace. */}
        <div
          className={clientFrame ? "px-6 pt-6 empty:p-0" : "mb-6 empty:mb-0"}
        >
          <AiStatusBanner />
        </div>
        {children}
      </main>
    </div>
  );
}
