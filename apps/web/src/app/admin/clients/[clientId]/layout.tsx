import { loadClientFrame } from "@/lib/admin/client-route";

import type { JSX } from "react";

/**
 * T6: every page under one client's frame is for that client. The layout
 * checks the client itself, but it is NOT the guard for its pages: a page's
 * own server reads run whatever the layout decides, so every page under here
 * calls `loadClientFrame` too. #1385: the client's rail is no longer rendered
 * here; the admin shell shows it in its left column (the `@rail` slot).
 */
export default async function ClientLayout(props: {
  params: Promise<{ clientId: string }>;
  children: React.ReactNode;
}): Promise<JSX.Element> {
  const { clientId } = await props.params;
  await loadClientFrame(clientId);
  return <>{props.children}</>;
}
