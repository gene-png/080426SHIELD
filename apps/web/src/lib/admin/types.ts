/**
 * Wire types mirroring apps/api/app/schemas/admin.py.
 */

import type { ClientProfileResponse, ServiceType } from "@/lib/intake/types";

/** Mirrors AdminServiceDetail in apps/api/app/schemas/admin.py. */
export interface AdminServiceDetail {
  id: string;
  kind: string;
  status: string;
  title: string;
  client_id: string;
}

export interface AdminUserSummary {
  id: string;
  email: string;
  display_name: string | null;
  title: string | null;
  role: "admin" | "client";
  last_login_at: string | null;
  created_at: string;
}

export interface AdminServiceRequestRow {
  id: string;
  service_type: ServiceType;
  requested_at: string;
  requested_by: AdminUserSummary;
  notes: string | null;
  deadline: string | null;
  csf_target_tier: number | null;
  csf_profile: string | null;
  zt_target_stage: number | null;
  fulfilled_service_id: string | null;
  declined_at: string | null;
  declined_reason: string | null;
}

export interface AdminArtifactRow {
  id: string;
  title: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by: string;
  uploaded_at: string;
}

export interface AdminIntakeQueueResponse {
  client: ClientProfileResponse | null;
  intake_completed_at: string | null;
  service_requests: AdminServiceRequestRow[];
  artifacts: AdminArtifactRow[];
  total_users: number;
}

export interface FulfillServiceRequestResponse {
  service_id: string;
  service_type: ServiceType;
  title: string;
  already_fulfilled: boolean;
}

/** Per-service-type workspace route segment under /admin/services/{id}/. */
export const WORKSPACE_PATH: Record<ServiceType, string | null> = {
  tech_debt: "tech-debt",
  zero_trust_cisa: "zero-trust-cisa",
  zero_trust_dod: "zero-trust-dod",
  nist_csf: "csf",
  attack_coverage: "attack-coverage",
  consultation: null,
};

/** Workspace URL for a fulfilled request, or null when not applicable. */
export function workspaceHref(
  serviceType: ServiceType,
  serviceId: string | null,
): string | null {
  const seg = WORKSPACE_PATH[serviceType];
  if (!seg || !serviceId) return null;
  return `/admin/services/${serviceId}/${seg}`;
}
