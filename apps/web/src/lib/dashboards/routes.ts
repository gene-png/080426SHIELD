import type { ServiceType } from "@/lib/intake/types";

/**
 * Single source of truth for client dashboard routes.
 *
 * Both the /results list and the /home service grid link to dashboards; they
 * previously would have carried their own copy of this switch, which is exactly
 * how the two surfaces drift when a new dashboard ships. One helper, one map.
 *
 * Returns null for service kinds that have no dashboard route (consultation)
 * so callers must decide a fallback rather than emit a dead link.
 *
 * `nist_csf` used to be in that list. It was the only assessment service
 * without a client dashboard, so a client could see a CSF gap count on their
 * home page and had no way to open the results.
 */
/**
 * Every service kind, and the dashboard segment it maps to (null = none).
 *
 * A `Record<ServiceType, ...>` rather than a switch with a `default`, so adding
 * a service type is a COMPILE error here instead of a silent `null`. The switch
 * form gave no exhaustiveness check, which is how `nist_csf` stayed unreachable
 * — and why the test that "guards" this had to hand-write the list of kinds it
 * checks, which is the same gap one layer up.
 */
const DASHBOARD_SEGMENT: Record<ServiceType, string | null> = {
  attack_coverage: "attack",
  zero_trust_cisa: "zt",
  zero_trust_dod: "zt",
  tech_debt: "tech-debt",
  nist_csf: "csf",
  consultation: null,
};

export function dashboardPathFor(
  serviceKind: string,
  serviceId: string,
): string | null {
  const segment = Object.prototype.hasOwnProperty.call(
    DASHBOARD_SEGMENT,
    serviceKind,
  )
    ? DASHBOARD_SEGMENT[serviceKind as ServiceType]
    : null;
  return segment === null ? null : `/dashboards/${segment}/${serviceId}`;
}
