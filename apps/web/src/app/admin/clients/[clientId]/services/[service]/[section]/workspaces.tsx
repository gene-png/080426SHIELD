import { AttackWorkspace } from "@/components/admin/attack/AttackWorkspace";
import { CsfWorkspace } from "@/components/admin/csf/CsfWorkspace";
import { EnsureActiveClient } from "@/components/admin/EnsureActiveClient";
import { TechDebtWorkspace } from "@/components/admin/TechDebtWorkspace";
import { ZtWorkspace } from "@/components/admin/zt/ZtWorkspace";
import type { SectionKey } from "@/components/service-shell/SectionBar";
import type { FrameKind } from "@/components/service-shell/shellCopy";

import type { JSX } from "react";

/**
 * Frame first, content unchanged (#736 issuecomment-6204357376): until a
 * service's track moves its components into sections, every section renders
 * the existing workspace exactly as the old `/admin/services/{id}/...` page
 * did, with the same props and the same titles.
 *
 * `EnsureActiveClient` stays: the unchanged workspaces still make tenant
 * calls scoped by the active-client cookie, and it aligns that cookie to the
 * service's client on mount. That is the #1129 multi-tab gap, NARROWED here
 * (the frame's own reads use the URL's client) and NOT closed; each service
 * track closes it for its own calls when it moves its components. Tech Debt's
 * split (#1376) moved where its blocks render and not which client its calls
 * name, so its calls still rely on this, and #1129 stays open for them.
 */
export const WORKSPACE_TITLES: Record<FrameKind, string> = {
  tech_debt: "Technical Debt Review",
  attack_coverage: "MITRE ATT&CK Coverage Mapping",
  nist_csf: "NIST CSF 2.0 Assessment",
  zero_trust_cisa: "Zero Trust Assessment (CISA ZTMM 2.0)",
  zero_trust_dod: "Zero Trust Assessment (DoD ZTRA)",
};

function Workspace({
  kind,
  serviceId,
  section,
}: {
  kind: FrameKind;
  serviceId: string;
  section: SectionKey;
}): JSX.Element {
  const serviceTitle = WORKSPACE_TITLES[kind];
  switch (kind) {
    case "tech_debt":
      // #1376: Tech Debt is split; each section shows only its own blocks.
      return (
        <TechDebtWorkspace
          serviceId={serviceId}
          serviceTitle={serviceTitle}
          section={section}
        />
      );
    case "attack_coverage":
      return (
        <AttackWorkspace serviceId={serviceId} serviceTitle={serviceTitle} />
      );
    case "nist_csf":
      return <CsfWorkspace serviceId={serviceId} serviceTitle={serviceTitle} />;
    case "zero_trust_cisa":
      // #1379: Zero Trust is split; each section shows only its own blocks.
      return (
        <ZtWorkspace
          serviceId={serviceId}
          framework="cisa_ztmm_2_0"
          serviceTitle={serviceTitle}
          section={section}
        />
      );
    case "zero_trust_dod":
      return (
        <ZtWorkspace
          serviceId={serviceId}
          framework="dod_ztra"
          serviceTitle={serviceTitle}
          section={section}
        />
      );
  }
}

/**
 * The section's slot: the one place that decides what a section RENDERS. It
 * receives the URL's `section` (already checked against the kind by the
 * page). Which sections a kind has (`omittedSections` in `frameRoutes.ts`),
 * the header's `next` and the page title are still the frame's. Tech Debt
 * is split (#1376): its workspace renders only the section's blocks. Until a
 * track moves the other services' components, each of their sections shows
 * the whole existing workspace, once, and `section` only names the slot.
 */
export function ExistingWorkspace({
  kind,
  serviceId,
  section,
}: {
  kind: FrameKind;
  serviceId: string;
  section: SectionKey;
}): JSX.Element {
  return (
    <div data-testid="section-view" data-section={section}>
      <EnsureActiveClient serviceId={serviceId}>
        <Workspace kind={kind} serviceId={serviceId} section={section} />
      </EnsureActiveClient>
    </div>
  );
}
