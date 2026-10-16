import type { Metadata } from "next";
import { cookies } from "next/headers";

import { IntakeWizard } from "@/components/intake/IntakeWizard";
import { ACTIVE_CLIENT_COOKIE } from "@/lib/api";

import type { JSX } from "react";

export const metadata: Metadata = {
  title: "Intake",
};

/**
 * #1262, the `/intake` residual (review of 69fbc5b1): the wizard pins the
 * client it LOADED on every later call. The header's client switcher sets the
 * active-client cookie and calls `router.refresh()`, which keeps client
 * component state, so without a key the wizard would stay pinned to the old
 * client while the header named the new one. Keyed on the active client, the
 * refresh remounts the wizard and it loads the new client.
 */
export default async function IntakePage(): Promise<JSX.Element> {
  const active = (await cookies()).get(ACTIVE_CLIENT_COOKIE)?.value ?? "";
  return <IntakeWizard key={active} />;
}
