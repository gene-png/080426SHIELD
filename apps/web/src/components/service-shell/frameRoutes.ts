/**
 * T6, the client-scoped navigation frame: its URL tables and the pure helpers
 * the rail (a client component) and the server pages share. Nothing here reads
 * the network or the cookie; the server checks are in `lib/admin/client-route.ts`.
 */
import { SECTIONS, type SectionKey } from "./SectionBar";
import { SHELL_COPY, type FrameKind } from "./shellCopy";
import { WORKSPACE_PATH } from "@/lib/admin/types";

/** The Risk Register's slug: a client-level page, not a `Service` row. */
export const RISK_REGISTER_SLUG = "risk-register";

/** Rail and overview order (the spec's slug order). */
export const KIND_ORDER: readonly FrameKind[] = [
  "tech_debt",
  "attack_coverage",
  "zero_trust_cisa",
  "zero_trust_dod",
  "nist_csf",
];

/**
 * A kind's URL slug. DERIVED from `WORKSPACE_PATH`, the old workspace routes'
 * table, so the old and new URLs cannot name a kind differently.
 */
export function slugForKind(kind: FrameKind): string {
  const slug = WORKSPACE_PATH[kind];
  if (!slug) throw new Error(`slugForKind: no slug for "${kind}"`);
  return slug;
}

export function kindForSlug(slug: string): FrameKind | null {
  return KIND_ORDER.find((k) => WORKSPACE_PATH[k] === slug) ?? null;
}

/** Page-plan decision 1: CSF and Zero Trust fold Inputs into AI draft. */
export function omittedSections(kind: FrameKind): readonly SectionKey[] {
  return kind === "tech_debt" || kind === "attack_coverage" ? [] : ["inputs"];
}

export function isSectionOf(kind: FrameKind, section: string): boolean {
  return SECTIONS.some(
    (s) => s.key === section && !omittedSections(kind).includes(s.key),
  );
}

export function clientHref(clientId: string): string {
  return `/admin/clients/${encodeURIComponent(clientId)}`;
}

export function riskRegisterHref(clientId: string): string {
  return `${clientHref(clientId)}/services/${RISK_REGISTER_SLUG}`;
}

/** A section's URL. Frame links always carry the service id (plan: a client
 * can have several services of one kind, and a bookmark must not switch). */
export function sectionHref(
  clientId: string,
  kind: FrameKind,
  section: SectionKey,
  serviceId: string | null,
): string {
  const base = `${clientHref(clientId)}/services/${slugForKind(kind)}/${section}`;
  return serviceId ? `${base}?service=${encodeURIComponent(serviceId)}` : base;
}

/** One of the client's services, as `GET /intake/engagements` lists it. */
export interface FrameService {
  service_id: string;
  service_type: FrameKind;
  status: string;
  created_at: string;
}

export interface ClientFrame {
  bearer: string;
  client: { id: string; label: string };
  services: FrameService[];
}

export const isOpen = (s: FrameService): boolean => s.status !== "archived";

/** A service's display name; dated when the client has more than one open
 * service of its kind. */
export function serviceName(s: FrameService, all: FrameService[]): string {
  const name = SHELL_COPY.serviceNames[s.service_type];
  const twins = all.filter(
    (x) => isOpen(x) && x.service_type === s.service_type,
  );
  return twins.length > 1 && isOpen(s)
    ? SHELL_COPY.duplicateName(name, s.created_at.slice(0, 10))
    : name;
}

/** Open services in rail order: by kind, then oldest first. */
export function railOrder(services: FrameService[]): FrameService[] {
  return services
    .filter(isOpen)
    .sort(
      (a, b) =>
        KIND_ORDER.indexOf(a.service_type) -
          KIND_ORDER.indexOf(b.service_type) ||
        a.created_at.localeCompare(b.created_at),
    );
}
