import { ClientRail } from "@/components/service-shell/ClientRail";
import { ClientFrameBody } from "@/components/service-shell/ClientFrameBody";
import { loadClientFrame } from "@/lib/admin/client-route";

import type { JSX } from "react";

/**
 * T6: every page under one client's frame sits beside that client's rail. The
 * layout checks the client itself, but it is NOT the guard for its pages: a
 * page's own server reads run whatever the layout decides, so every page under
 * here calls `loadClientFrame` too. #1385: the rail is the admin page's left
 * column (`ClientFrameBody`).
 */
export default async function ClientLayout(props: {
  params: Promise<{ clientId: string }>;
  children: React.ReactNode;
}): Promise<JSX.Element> {
  const { clientId } = await props.params;
  const frame = await loadClientFrame(clientId);
  return (
    <ClientFrameBody
      rail={<ClientRail client={frame.client} services={frame.services} />}
    >
      {props.children}
    </ClientFrameBody>
  );
}
