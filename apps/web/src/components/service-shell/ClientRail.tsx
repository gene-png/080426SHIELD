"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { ClientNavPicker } from "./ClientNavPicker";
import {
  railOrder,
  riskRegisterHref,
  sectionHref,
  serviceName,
  type FrameService,
} from "./frameRoutes";
import { SHELL_COPY } from "./shellCopy";

import type { JSX } from "react";

/**
 * T6: the persistent left rail of ONE client's frame (#736
 * issuecomment-6204357376). The client's name and a picker that navigates to
 * another client's frame, then the client's open services, then the Risk
 * Register. The client is the URL's; the server layout checked it and read
 * these services with its id before rendering this.
 */
export type RailService = FrameService;

const LINK =
  "block rounded-md px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-surface-sunken hover:text-ink-primary";
const CURRENT =
  "block rounded-md px-3 py-2 text-sm font-medium bg-brand-50 text-brand-600";

function RailLinks({
  clientId,
  services,
  current,
}: {
  clientId: string;
  services: FrameService[];
  /** The service id on screen, or "risk-register", or null. */
  current: string | null;
}): JSX.Element {
  const open = railOrder(services);
  const rr = riskRegisterHref(clientId);
  return (
    <ul className="flex flex-col gap-1">
      {open.map((s) => (
        <li key={s.service_id}>
          <Link
            href={sectionHref(clientId, s.service_type, "overview", s.service_id)}
            aria-current={current === s.service_id ? "page" : undefined}
            className={current === s.service_id ? CURRENT : LINK}
          >
            {serviceName(s, services)}
          </Link>
        </li>
      ))}
      {open.length === 0 ? (
        <li className="px-3 py-2 text-sm text-ink-tertiary">
          <p>{SHELL_COPY.railEmpty}</p>
          <Link
            href={`/admin/queue/${encodeURIComponent(clientId)}`}
            className="font-medium text-brand-600 underline hover:text-brand-700"
          >
            {SHELL_COPY.railEmptyLink}
          </Link>
        </li>
      ) : null}
      <li>
        <Link
          href={rr}
          aria-current={current === "risk-register" ? "page" : undefined}
          className={current === "risk-register" ? CURRENT : LINK}
        >
          {SHELL_COPY.riskRegister}
        </Link>
      </li>
    </ul>
  );
}

/** Which rail entry the URL is on. Inside Suspense: it reads search params. */
function CurrentRailLinks({
  clientId,
  services,
}: {
  clientId: string;
  services: FrameService[];
}): JSX.Element {
  const pathname = usePathname() ?? "";
  const params = useSearchParams();
  const current = pathname.startsWith(riskRegisterHref(clientId))
    ? "risk-register"
    : (params?.get("service") ?? null);
  return (
    <RailLinks clientId={clientId} services={services} current={current} />
  );
}

export function ClientRail({
  client,
  services,
}: {
  client: { id: string; label: string };
  services: FrameService[];
}): JSX.Element {
  return (
    <aside className="flex w-56 shrink-0 flex-col gap-3">
      <div className="flex flex-col gap-2">
        <p className="text-base font-semibold text-ink-primary">
          {client.label}
        </p>
        <ClientNavPicker currentId={client.id} />
      </div>
      <nav aria-label={SHELL_COPY.railNavName}>
        <Suspense
          fallback={
            <RailLinks clientId={client.id} services={services} current={null} />
          }
        >
          <CurrentRailLinks clientId={client.id} services={services} />
        </Suspense>
      </nav>
    </aside>
  );
}
