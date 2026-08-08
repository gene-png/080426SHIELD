"use client";
import { SessionProvider } from "next-auth/react";
import * as React from "react";

import { SessionExpiryGuard } from "@/components/auth/SessionExpiryGuard";
import { SessionExpiryWarning } from "@/components/auth/SessionExpiryWarning";

import type { JSX } from "react";

/**
 * Thin wrapper - NextAuth's `SessionProvider` is a Client Component, so
 * keep it isolated in its own file rather than marking the entire layout
 * "use client". Hosts the SessionExpiryGuard so the forced-reauth signal is
 * handled app-wide, and the SessionExpiryWarning so the countdown reaches every
 * signed-in page — client and admin alike — rather than only the ones someone
 * remembered to wire it into.
 */
export function AuthSessionProvider({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <SessionProvider>
      <SessionExpiryGuard />
      <SessionExpiryWarning />
      {children}
    </SessionProvider>
  );
}
