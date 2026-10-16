import Link from "next/link";

import {
  isOpen,
  railOrder,
  riskRegisterHref,
  sectionHref,
  serviceName,
  type FrameService,
} from "@/components/service-shell/frameRoutes";
import { SHELL_COPY } from "@/components/service-shell/shellCopy";
import { loadClientFrame } from "@/lib/admin/client-route";

import type { JSX } from "react";

/**
 * T6: one client's overview. Its services with their status, archived ones
 * listed apart (archiving hides nothing elsewhere, so they stay reachable),
 * and the Risk Register. Not the portfolio page, which is post-MVP.
 */
export default async function ClientOverviewPage(props: {
  params: Promise<{ clientId: string }>;
}): Promise<JSX.Element> {
  const { clientId } = await props.params;
  const frame = await loadClientFrame(clientId);
  const open = railOrder(frame.services);
  const archived = frame.services.filter((s) => !isOpen(s));

  function row(s: FrameService): JSX.Element {
    return (
      <li key={s.service_id} className="flex items-center gap-3">
        <Link
          href={sectionHref(clientId, s.service_type, "overview", s.service_id)}
          className="font-medium text-brand-600 underline hover:text-brand-700"
        >
          {serviceName(s, frame.services)}
        </Link>
        <span className="text-sm text-ink-secondary">
          {SHELL_COPY.status[s.status] ?? s.status}
        </span>
      </li>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-ink-primary">
        {frame.client.label}
      </h1>
      <section className="flex flex-col gap-2">
        <h2
          id="client-services"
          className="text-lg font-semibold text-ink-primary"
        >
          {SHELL_COPY.overviewServicesHeading}
        </h2>
        <ul aria-labelledby="client-services" className="flex flex-col gap-2">
          {open.map(row)}
        </ul>
        {open.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            {SHELL_COPY.railEmpty}{" "}
            <Link
              href={`/admin/queue/${encodeURIComponent(clientId)}`}
              className="font-medium text-brand-600 underline hover:text-brand-700"
            >
              {SHELL_COPY.railEmptyLink}
            </Link>
          </p>
        ) : null}
        <p>
          <Link
            href={riskRegisterHref(clientId)}
            className="font-medium text-brand-600 underline hover:text-brand-700"
          >
            {SHELL_COPY.riskRegister}
          </Link>
        </p>
      </section>
      {archived.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2
            id="client-archived"
            className="text-lg font-semibold text-ink-primary"
          >
            {SHELL_COPY.archivedHeading}
          </h2>
          <ul aria-labelledby="client-archived" className="flex flex-col gap-2">
            {archived.map(row)}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
