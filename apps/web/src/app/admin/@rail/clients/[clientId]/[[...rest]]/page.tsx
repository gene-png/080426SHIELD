import { ClientRail } from "@/components/service-shell/ClientRail";
import { loadClientFrame } from "@/lib/admin/client-route";

import type { JSX } from "react";

/**
 * #1385: the client's rail, in the admin shell's left column. It was the
 * client layout's own column; a parallel slot lets the shell place it. Like
 * that layout it checks the client itself and is NOT the guard for its pages:
 * every page under `/admin/clients/<id>` calls `loadClientFrame` too.
 */
export default async function ClientRailSlot(props: {
  params: Promise<{ clientId: string }>;
}): Promise<JSX.Element> {
  const { clientId } = await props.params;
  const frame = await loadClientFrame(clientId);
  return <ClientRail client={frame.client} services={frame.services} />;
}
