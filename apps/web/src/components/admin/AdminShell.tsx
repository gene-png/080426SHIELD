"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AiStatusBanner } from "@/components/admin/AiStatusBanner";
import { SignOutButton } from "@/components/site/SignOutButton";
import { SkipToContent } from "@/components/site/SkipToContent";

import type { JSX } from "react";

/**
 * Admin shell (Navigation_Spec §2): a persistent left sidebar so an admin can
 * jump anywhere from anywhere, a header carrying the signed-in identity, and a
 * skip-to-content link. The sidebar never disappears inside a workspace.
 */

interface NavItem {
  label: string;
  href: string;
}

const NAV: NavItem[] = [
  { label: "Intake Queue", href: "/admin/queue" },
  { label: "Deliverables", href: "/admin/deliverables" },
  { label: "Risk Register", href: "/admin/risk-register" },
  { label: "Messages", href: "/admin/messages" },
  { label: "Audit", href: "/admin/audit" },
  { label: "System Health", href: "/admin/health" },
  { label: "Management", href: "/admin/management" },
];

/**
 * RR-2 (for #1121), design note §3.6: the three pages that share a client
 * picker. Moving between them keeps the chosen client: while the current page
 * is one of them and its URL has `client`, their sidebar links carry the same
 * value. The shell judges nothing (it reads no client list and never the
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

function SidebarLinks({
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

function MobileLinks({
  pathname,
  client,
}: {
  pathname: string;
  client: string | null;
}): JSX.Element {
  return (
    <>
      {NAV.map((item) => (
        <Link
          key={item.href}
          href={navHref(item.href, pathname, client)}
          className="font-medium text-ink-secondary hover:text-ink-primary"
        >
          {item.label}
        </Link>
      ))}
    </>
  );
}

/**
 * Reads the URL's `client`. It sits inside a Suspense boundary whose fallback
 * renders the same links with bare hrefs, so the sidebar never disappears.
 */
function WithClientParam({
  children,
}: {
  children: (client: string | null) => React.ReactNode;
}): JSX.Element {
  const params = useSearchParams();
  return <>{children(params?.get("client") ?? null)}</>;
}

/**
 * #1050: a service workspace (`/admin/services/<id>/...`) carries wide
 * editable tables, so it runs full-width. List and form pages keep the
 * readable `max-w-6xl` cap.
 */
function isWorkspace(pathname: string): boolean {
  return /^\/admin\/services\/[^/]+\/.+/.test(pathname);
}

export function AdminShell({
  email,
  children,
}: {
  email?: string | null;
  children: React.ReactNode;
}): JSX.Element {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-surface-sunken">
      <SkipToContent />
      <div className="flex min-h-screen">
        <aside
          className="hidden w-60 shrink-0 flex-col border-r border-border-subtle bg-surface-card md:flex"
          aria-label="Admin navigation"
        >
          <Link
            href="/admin/queue"
            className="flex flex-col px-5 py-4 leading-tight"
          >
            <span className="text-lg font-semibold tracking-tight text-ink-primary">
              SHIELD
            </span>
            <span className="text-xs font-medium uppercase tracking-wider text-ink-tertiary">
              Admin console
            </span>
          </Link>
          <nav className="flex flex-col gap-1 px-3 py-2" aria-label="Primary">
            <Suspense
              fallback={<SidebarLinks pathname={pathname} client={null} />}
            >
              <WithClientParam>
                {(client) => (
                  <SidebarLinks pathname={pathname} client={client} />
                )}
              </WithClientParam>
            </Suspense>
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-border-subtle bg-surface-card px-6 py-3">
            {/* Mobile-only inline nav so the sidebar's destinations stay reachable. */}
            <nav
              className="flex items-center gap-3 text-sm md:hidden"
              aria-label="Primary"
            >
              <Suspense
                fallback={<MobileLinks pathname={pathname} client={null} />}
              >
                <WithClientParam>
                  {(client) => (
                    <MobileLinks pathname={pathname} client={client} />
                  )}
                </WithClientParam>
              </Suspense>
            </nav>
            <div className="ml-auto flex items-center gap-3">
              {email ? (
                <span className="text-xs text-ink-tertiary">{email}</span>
              ) : null}
              <SignOutButton />
            </div>
          </header>
          <main
            id="main-content"
            tabIndex={-1}
            className={
              "mx-auto w-full px-6 py-8 focus:outline-2 focus:outline-offset-4 focus:outline-brand-500 " +
              (isWorkspace(pathname) ? "" : "max-w-6xl")
            }
          >
            {/* Issue 2: shell-level so the warning is visible on every admin
                page including the landing one, not just one workspace. */}
            <div className="mb-6 empty:mb-0">
              <AiStatusBanner />
            </div>
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
