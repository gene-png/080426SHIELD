import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import {
  clientHref,
  isSectionOf,
  kindForSlug,
  omittedSections,
  RISK_REGISTER_SLUG,
  railOrder,
  riskRegisterHref,
  sectionHref,
  serviceName,
  type ClientFrame,
  type FrameService,
} from "@/components/service-shell/frameRoutes";
import {
  SectionBar,
  type SectionKey,
} from "@/components/service-shell/SectionBar";
import { ServiceHeader } from "@/components/service-shell/ServiceHeader";
import {
  SHELL_COPY,
  stageLabel,
  type FrameKind,
} from "@/components/service-shell/shellCopy";
import { loadClientFrame } from "@/lib/admin/client-route";
import { apiFetch } from "@/lib/api";

import { ExistingWorkspace, WORKSPACE_TITLES } from "./workspaces";

import type { JSX } from "react";

interface Params {
  clientId: string;
  service: string;
  section: string;
}

export async function generateMetadata(props: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const kind = kindForSlug((await props.params).service);
  return kind ? { title: WORKSPACE_TITLES[kind] } : {};
}

/**
 * T6: one section of one service in a client's frame. The checks, in order,
 * each refusing with `notFound()` before anything renders:
 * 1. an admin session, the URL's client, and its services read with ITS id
 *    (`loadClientFrame`);
 * 2. the slug names a service kind and the section is one that kind has;
 * 3. `?service` is one of THIS client's services and of THIS kind.
 * With no `?service`, the page picks the one open service of the kind, lists
 * them when there are several, or says the kind is not open.
 */
export default async function SectionPage(props: {
  params: Promise<Params>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<JSX.Element> {
  const { clientId, service, section } = await props.params;
  const query = await props.searchParams;

  if (service === RISK_REGISTER_SLUG) redirect(riskRegisterHref(clientId));
  const kind = kindForSlug(service);
  if (!kind || !isSectionOf(kind, section)) {
    console.warn("[client_frame] refused: no such section", service, section);
    notFound();
  }
  const frame = await loadClientFrame(clientId);
  const sectionKey = section as SectionKey;
  const asked = typeof query.service === "string" ? query.service : null;

  if (asked === null) {
    const open = railOrder(frame.services).filter(
      (s) => s.service_type === kind,
    );
    if (open.length === 1)
      redirect(sectionHref(clientId, kind, sectionKey, open[0].service_id));
    return open.length === 0 ? (
      <NotOpen frame={frame} kind={kind} />
    ) : (
      <Chooser frame={frame} kind={kind} section={sectionKey} open={open} />
    );
  }

  const svc = frame.services.find(
    (s) => s.service_id === asked && s.service_type === kind,
  );
  if (!svc) {
    console.warn(
      "[client_frame] refused: service is not this client's of this kind",
      clientId,
      asked,
      kind,
    );
    notFound();
  }

  console.info("[client_frame] section", clientId, svc.service_id, section);
  return (
    <div className="flex flex-col">
      {await header(frame, svc)}
      <SectionBar
        current={sectionKey}
        omit={omittedSections(kind)}
        hrefFor={(key) => sectionHref(clientId, kind, key, svc.service_id)}
      />
      <div className="mt-6">
        <ExistingWorkspace
          kind={kind}
          serviceId={svc.service_id}
          section={sectionKey}
        />
      </div>
    </div>
  );
}

interface StagesBody {
  version: number | null;
  stages: { key: string; state: string }[];
}

/** The stage on screen: the current one, else the last complete one. */
function currentStage(body: StagesBody, kind: FrameKind): string {
  const current =
    body.stages.find((s) => s.state === "current") ??
    [...body.stages].reverse().find((s) => s.state === "complete");
  if (!current) throw new Error("client_frame: stages carry no current stage");
  return stageLabel(current.key, kind);
}

/**
 * The service header. Its read is the frame's, scoped to the URL's client. A
 * failure is SHOWN, in place of the header, and the workspace still renders:
 * losing the version line must not lose the workspace under it.
 */
async function header(
  frame: ClientFrame,
  svc: FrameService,
): Promise<JSX.Element> {
  const kind = svc.service_type;
  const overviewHref = sectionHref(
    frame.client.id,
    kind,
    "overview",
    svc.service_id,
  );
  let facts: { version: string; stage: string };
  try {
    const body = await apiFetch<StagesBody>(
      `/services/${encodeURIComponent(svc.service_id)}/stages`,
      { bearer: frame.bearer, clientId: frame.client.id },
    );
    facts = {
      version: SHELL_COPY.version(body.version),
      stage: currentStage(body, kind),
    };
  } catch (err) {
    console.error(
      "[client_frame] service header read failed",
      svc.service_id,
      err,
    );
    return (
      <div className="border-b border-border-subtle bg-surface-card px-6 py-3">
        <Link
          href={overviewHref}
          className="text-base font-semibold text-ink-primary hover:text-brand-600"
        >
          {SHELL_COPY.serviceNames[kind]}
        </Link>
        <p role="alert" className="text-sm text-status-danger-fg">
          {SHELL_COPY.headerFailed}
        </p>
      </div>
    );
  }
  return (
    <ServiceHeader
      serviceTitle={SHELL_COPY.serviceNames[kind]}
      overviewHref={overviewHref}
      version={facts.version}
      status={SHELL_COPY.status[svc.status] ?? svc.status}
      stage={facts.stage}
      next={null}
    />
  );
}

function NotOpen({
  frame,
  kind,
}: {
  frame: ClientFrame;
  kind: FrameKind;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-primary">
        {SHELL_COPY.notOpen(SHELL_COPY.serviceNames[kind])}
      </p>
      <Link
        href={clientHref(frame.client.id)}
        className="font-medium text-brand-600 underline hover:text-brand-700"
      >
        {SHELL_COPY.backTo(frame.client.label)}
      </Link>
    </div>
  );
}

function Chooser({
  frame,
  kind,
  section,
  open,
}: {
  frame: ClientFrame;
  kind: FrameKind;
  section: SectionKey;
  open: FrameService[];
}): JSX.Element {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-ink-primary">
        {SHELL_COPY.chooser(
          frame.client.label,
          open.length,
          SHELL_COPY.serviceNames[kind],
        )}
      </p>
      <ul className="flex flex-col gap-2">
        {open.map((s) => (
          <li key={s.service_id}>
            <Link
              href={sectionHref(frame.client.id, kind, section, s.service_id)}
              className="font-medium text-brand-600 underline hover:text-brand-700"
            >
              {serviceName(s, frame.services)}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
