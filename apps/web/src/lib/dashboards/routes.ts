import type { ServiceType } from "@/lib/intake/types";

/**
 * Single source of truth for client dashboard routes.
 *
 * Both the /results list and the /home service grid link to dashboards; they
 * previously would have carried their own copy of this switch, which is exactly
 * how the two surfaces drift when a new dashboard ships. One helper, one map.
 *
 * Returns null for service kinds that have no dashboard route (nist_csf and
 * consultation) so callers must decide a fallback rather than emit a dead link.
 */
export function dashboardPathFor(
  serviceKind: string,
  serviceId: string,
): string | null {
  switch (serviceKind as ServiceType) {
    case "attack_coverage":
      return `/dashboards/attack/${serviceId}`;
    case "zero_trust_cisa":
    case "zero_trust_dod":
      return `/dashboards/zt/${serviceId}`;
    case "tech_debt":
      return `/dashboards/tech-debt/${serviceId}`;
    default:
      return null;
  }
}
