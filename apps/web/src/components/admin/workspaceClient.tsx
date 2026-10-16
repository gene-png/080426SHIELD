"use client";
import * as React from "react";

import type { JSX } from "react";

/*
 * Its own module, apart from EnsureActiveClient, on purpose: client-facing
 * components (the intake Dropzone) read the hook, and importing
 * EnsureActiveClient itself would pull its admin error copy into the
 * client-surface graph that `client-surfaces-never-render-an-internal-string`
 * sweeps.
 */

/**
 * #1129: the client this workspace was opened for, as EnsureActiveClient resolves it. The
 * active-client cookie is shared by every tab, so a component that refetches
 * after mount must name THIS id rather than trust the cookie, which another
 * tab may have rewritten. Null outside a workspace.
 */
const WorkspaceClientContext = React.createContext<string | null>(null);

export function WorkspaceClientProvider({
  clientId,
  children,
}: {
  clientId: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <WorkspaceClientContext.Provider value={clientId}>
      {children}
    </WorkspaceClientContext.Provider>
  );
}

/** The workspace's own client id, or null outside an EnsureActiveClient. */
export function useWorkspaceClientId(): string | null {
  return React.useContext(WorkspaceClientContext);
}
