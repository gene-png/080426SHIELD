/**
 * T6 (navigation frame) shell copy, in ONE module.
 *
 * APPROVED verbatim on #736 (issuecomment-6206422365 item 4): items 1-11 as
 * posted in issuecomment-6204457912, items 12-13 as posted in
 * issuecomment-6205501155. A wording change here goes back for approval.
 */
import type { ServiceType } from "@/lib/intake/types";

/** A service kind a client can have open: every `ServiceType` but consultation. */
export type FrameKind = Exclude<ServiceType, "consultation">;

export const SHELL_COPY = {
  /** 1. Admin sidebar item. */
  navClients: "Clients",
  /** 2. `/admin/clients`. */
  clientsHeading: "Clients",
  clientsLine: "Choose a client to open its services.",
  /** 3. The rail's accessible name. */
  railNavName: "Client services",
  /** 4. Service names in the rail, the overview and the chooser. */
  serviceNames: {
    tech_debt: "Technical Debt Review",
    attack_coverage: "MITRE ATT&CK Coverage",
    zero_trust_cisa: "Zero Trust (CISA ZTMM 2.0)",
    zero_trust_dod: "Zero Trust (DoD ZTRA)",
    nist_csf: "NIST CSF 2.0",
  } satisfies Record<FrameKind, string>,
  riskRegister: "Risk Register",
  /** 5. A kind the client has more than one of. `date` is YYYY-MM-DD. */
  duplicateName: (name: string, date: string) => `${name}, started ${date}`,
  /** 6. The client has no service open. */
  railEmpty: "No services are open for this client yet.",
  railEmptyLink: "Open the intake queue",
  /** 7. Client overview. */
  archivedHeading: "Archived services",
  /** 8. A service URL whose kind this client does not have. */
  notOpen: (name: string) => `${name} is not open for this client.`,
  backTo: (client: string) => `Back to ${client}`,
  /** 9. A service URL with no id, for a kind the client has several of. */
  chooser: (client: string, n: number, name: string) =>
    `${client} has ${n} ${name} services. Choose one.`,
  /** 10. Service header values. The labels are ServiceHeader's own. */
  version: (n: number | null) => (n === null ? "Not started" : `v${n}`),
  status: {
    draft: "Draft",
    in_progress: "In progress",
    review: "In review",
    released: "Released",
    archived: "Archived",
  } as Record<string, string>,
  /** 11. The header's read failed; the workspace still renders below it. */
  headerFailed: "The version, status and stage could not be loaded.",
  /** 12 (new). Client overview, the heading over the open services. */
  overviewServicesHeading: "Services",
  /** 13 (new). The picker when there are no clients (ClientSwitcher's words). */
  pickerNone: "No clients yet",
} as const;

/**
 * The stage words, a TWIN of `ProgressStages`' private labels, copied because
 * that component is outside T6's file area. `shellCopy.test.tsx` renders
 * `ProgressStages` and requires every label here to match what it shows, so
 * the two cannot drift silently.
 */
export const STAGE_LABELS: Record<string, string> = {
  prepare: "Prepare",
  analyze: "Analyze",
  review: "Review",
  approve: "Approve",
  generate: "Generate",
  release: "Release",
};

/** `ProgressStages`' rule: CSF and ZT's `prepare` waits on the client. */
export function stageLabel(key: string, kind: FrameKind): string {
  if (key === "prepare" && kind !== "tech_debt" && kind !== "attack_coverage")
    return "Self-assessment";
  const label = STAGE_LABELS[key];
  if (!label) throw new Error(`stageLabel: unknown stage key "${key}"`);
  return label;
}
