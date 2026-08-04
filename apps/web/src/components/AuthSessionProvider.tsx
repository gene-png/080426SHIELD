"use client";
import { SessionProvider } from "next-auth/react";
import * as React from "react";

import { SessionExpiryGuard } from "@/components/auth/SessionExpiryGuard";

import type { JSX } from "react";

/**
 * Thin wrapper - NextAuth's `SessionProvider` is a Client Component, so
 * keep it isolated in its own file rather than marking the entire layout
 * "use client". Hosts the SessionExpiryGuard so the forced-reauth signal is
 * handled app-wide.
 */
export function AuthSessionProvider({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  return (
    <SessionProvider>
      <SessionExpiryGuard />
      {children}
    </SessionProvider>
  );
}
