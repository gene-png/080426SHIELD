/**
 * Wire types matching apps/api/app/schemas/intake.py.
 *
 * Kept in app/lib so they're consumable from both Server and Client
 * Components without dragging a separate package import path.
 */

export type ServiceType =
  | "tech_debt"
  | "zero_trust_cisa"
  | "zero_trust_dod"
  | "nist_csf"
  | "attack_coverage"
  | "consultation";

export interface ClientProfileResponse {
  id: string;
  legal_name: string;
  dba_name: string | null;
  website: string | null;
  size_band: string | null;
  industry: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  prompting_context: string | null;
  service_interests: string[] | null;
  intake_completed_at: string | null;
  /**
   * Primary-contact override (migration 0039). All null means the contact is
   * whoever submitted the intake — which is what every pre-0039 client means.
   */
  primary_contact_name?: string | null;
  primary_contact_email?: string | null;
  primary_contact_title?: string | null;
  primary_contact_phone?: string | null;
}

export type CsfProfile = "LOW" | "MOD" | "HIGH";

export interface ServiceRequestResponse {
  id: string;
  service_type: ServiceType;
  requested_by: string;
  requested_at: string;
  notes: string | null;
  deadline: string | null;
  csf_target_tier: number | null;
  csf_profile: string | null;
  zt_target_stage: number | null;
  fulfilled_service_id: string | null;
  declined_at: string | null;
  declined_reason: string | null;
}

export interface IntakeContactResponse {
  display_name: string | null;
  email: string;
  title: string | null;
  phone: string | null;
  timezone: string | null;
  /** These details came from the override, not the submitting user's account. */
  is_override?: boolean;
}

export interface IntakeStateResponse {
  client: ClientProfileResponse | null;
  service_requests: ServiceRequestResponse[];
  intake_completed_at: string | null;
  /** The primary contact, so Review & submit can show what is being sent. */
  contact?: IntakeContactResponse | null;
}

/** One assessment = one Service (workspace) the client owns. */
export interface AssessmentResponse {
  service_id: string;
  service_type: ServiceType;
  title: string;
  status: string;
  assessment_status: string | null;
  created_at: string;
}

export interface AssessmentCreateRequest {
  service_type: ServiceType;
  name?: string;
  csf_target_tier?: number;
  csf_profile?: CsfProfile;
  zt_target_stage?: number;
}

/** Service types a client can self-start as a standalone assessment. */
export const ASSESSMENT_SERVICE_TYPES: ReadonlyArray<ServiceType> = [
  "nist_csf",
  "zero_trust_cisa",
  "zero_trust_dod",
];

export interface ClientProfilePatch {
  legal_name?: string;
  dba_name?: string;
  website?: string;
  size_band?: string;
  industry?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
  prompting_context?: string;
  service_interests?: ServiceType[];
  /**
   * Primary-contact override (migration 0039). Explicitly nullable, unlike the
   * fields above: clearing "I am not the primary contact" has to SEND null to
   * erase a stored override, and an optional-undefined field cannot say that.
   */
  primary_contact_name?: string | null;
  primary_contact_email?: string | null;
  primary_contact_title?: string | null;
  primary_contact_phone?: string | null;
}

export interface IntakePatchRequest {
  client?: ClientProfilePatch;
  display_name?: string;
  title?: string;
  phone?: string;
  timezone?: string;
}

export interface ServiceRequestInput {
  service_type: ServiceType;
  notes?: string;
  deadline?: string;
  csf_target_tier?: number;
  csf_profile?: CsfProfile;
  zt_target_stage?: number;
}

export interface IntakeSubmitRequest {
  client: ClientProfilePatch;
  service_requests: ServiceRequestInput[];
  display_name?: string;
  title?: string;
  phone?: string;
  timezone?: string;
}

/**
 * One-line explanation of each service, in client-facing language.
 *
 * Shared deliberately: the intake picker and the /help page must describe a
 * service the same way, and the surest way to guarantee that is one definition.
 * This lived privately inside Step1Services.tsx until the Help surface needed
 * it (IA appendix: "Messages / Help — service explanations").
 *
 * Intake-only mechanics do NOT belong here — Step1Services appends its own
 * "selecting this clears the other picks" hint, because that sentence is about
 * the wizard, not about the service.
 */
export const SERVICE_DESCRIPTIONS: Record<ServiceType, string> = {
  tech_debt:
    "Inventory your security stack, surface overlap and gaps, ship a consolidation plan.",
  zero_trust_cisa:
    "Score current and target maturity per pillar against CISA Zero Trust Maturity Model 2.0.",
  zero_trust_dod:
    "Score current and target maturity per pillar against DoD Zero Trust Reference Architecture.",
  nist_csf:
    "Full 10-step NIST CSF 2.0 Playbook with tiered profiles, 5-dimension scoring, gap plan.",
  attack_coverage:
    "Score the full MITRE ATT&CK Enterprise matrix against your approved capability list.",
  consultation:
    "A guided conversation to scope which services fit your organization.",
};

export const SERVICE_LABELS: Record<ServiceType, string> = {
  tech_debt: "Technical Debt Review",
  zero_trust_cisa: "Zero Trust Assessment (CISA ZTMM 2.0)",
  zero_trust_dod: "Zero Trust Assessment (DoD ZTRA)",
  nist_csf: "NIST CSF 2.0 Assessment",
  attack_coverage: "MITRE ATT&CK Coverage Mapping",
  consultation: "I'm not sure — start with a consultation",
};

/**
 * Client-set assessment targets. Labels mirror the backend source of truth
 * (apps/api/app/csf/maturity.py, apps/api/app/zt/maturity.py). Tier/Stage 1 is
 * the floor, so a client only ever targets 2-4.
 */
export const CSF_TARGET_TIERS: ReadonlyArray<{ value: number; label: string }> =
  [
    { value: 2, label: "Tier 2 · Risk Informed" },
    { value: 3, label: "Tier 3 · Repeatable" },
    { value: 4, label: "Tier 4 · Adaptive" },
  ];

export const CSF_PROFILES: ReadonlyArray<{ value: CsfProfile; label: string }> =
  [
    { value: "LOW", label: "Low impact" },
    { value: "MOD", label: "Moderate impact" },
    { value: "HIGH", label: "High impact" },
  ];

export const ZT_TARGET_STAGES: Record<
  "zero_trust_cisa" | "zero_trust_dod",
  ReadonlyArray<{ value: number; label: string }>
> = {
  zero_trust_cisa: [
    { value: 2, label: "Stage 2 · Initial" },
    { value: 3, label: "Stage 3 · Advanced" },
    { value: 4, label: "Stage 4 · Optimal" },
  ],
  zero_trust_dod: [
    { value: 2, label: "Stage 2 · Target" },
    { value: 3, label: "Stage 3 · Advanced" },
    { value: 4, label: "Stage 4 · Optimal" },
  ],
};

/** True when `svc` needs client targets that `input` hasn't supplied yet. */
export function hasMissingTargets(
  svc: ServiceType,
  input: ServiceRequestInput | undefined,
): boolean {
  if (svc === "nist_csf") {
    return !input?.csf_target_tier || !input?.csf_profile;
  }
  if (svc === "zero_trust_cisa" || svc === "zero_trust_dod") {
    return !input?.zt_target_stage;
  }
  return false;
}

export const WIZARD_STEPS = [
  { key: "services", label: "Services" },
  { key: "organization", label: "Organization" },
  { key: "contact", label: "Contact" },
  { key: "systems", label: "Systems" },
  { key: "notes", label: "Notes & artifacts" },
  { key: "review", label: "Review & submit" },
] as const;

export type WizardStepKey = (typeof WIZARD_STEPS)[number]["key"];
