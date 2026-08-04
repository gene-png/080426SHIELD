"use client";
import { signOut } from "next-auth/react";

import type { JSX } from "react";

/**
 * Tears down all session state for this browser: clears the active-tenant
 * selection, deletes the NextAuth session cookie, then does a full-page load
 * to "/" so the server re-renders logged-out and no cached (authenticated)
 * RSC tree lingers.
 */
async function handleSignOut(): Promise<void> {
  // Drop the active-client cookie so a selected tenant doesn't carry over to
  // the next person who signs in on this browser.
  try {
    await fetch("/api/active-client", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId: null }),
    });
  } catch {
    /* best-effort */
  }
  // redirect:false so we await the cookie-clearing request, then hard-navigate.
  await signOut({ redirect: false });
  window.location.assign("/");
}

export function SignOutButton(): JSX.Element {
  return (
    <button
      type="button"
      onClick={() => void handleSignOut()}
      className="rounded-md px-3 py-2 font-medium text-ink-secondary hover:text-ink-primary"
    >
      Sign out
    </button>
  );
}
