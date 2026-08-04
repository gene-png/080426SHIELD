import type { Metadata } from "next";

import { IntakeQueue } from "@/components/admin/IntakeQueue";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Organization intake",
};

/**
 * Issue 7: one organization's intake — its submission details at the top, then
 * the pending work below. Scoped by `clientId` so the profile shown always
 * belongs to the requests listed underneath.
 */
export default async function AdminQueueClientPage({
  params,
}: {
  params: Promise<{ clientId: string }>;
}): Promise<JSX.Element> {
  const { clientId } = await params;
  return <IntakeQueue clientId={clientId} />;
}
