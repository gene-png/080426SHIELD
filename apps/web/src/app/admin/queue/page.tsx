import type { Metadata } from "next";

import { IntakeOrgIndex } from "@/components/admin/IntakeOrgIndex";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Intake queue",
};

/**
 * Issue 7: the queue landing page is now an ORGANIZATION INDEX. It used to
 * render one tenant's intake directly — whichever tenant was created most
 * recently — with every tenant's service requests below it. Pick an
 * organization here; /admin/queue/[clientId] shows its profile and its work.
 */
export default function AdminQueuePage(): JSX.Element {
  return <IntakeOrgIndex />;
}
