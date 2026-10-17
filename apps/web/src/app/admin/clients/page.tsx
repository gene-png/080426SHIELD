import { ClientNavPicker } from "@/components/service-shell/ClientNavPicker";
import { SHELL_COPY } from "@/components/service-shell/shellCopy";
import { requireAdminBearer } from "@/lib/admin/client-route";

import type { JSX } from "react";

/**
 * T6: the way into a client's frame. The picker alone; the full client
 * portfolio page (search, filters, summary numbers) is post-MVP.
 */
export default async function ClientsPage(): Promise<JSX.Element> {
  await requireAdminBearer();
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-ink-primary">
        {SHELL_COPY.clientsHeading}
      </h1>
      <p className="text-ink-secondary">{SHELL_COPY.clientsLine}</p>
      <ClientNavPicker currentId={null} />
    </div>
  );
}
