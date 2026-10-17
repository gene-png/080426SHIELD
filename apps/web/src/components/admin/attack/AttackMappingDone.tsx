import type { JSX } from "react";

import type { CatalogTechnique } from "@/lib/attack/types";

/**
 * #1182, Gene's 2026-10-15 test-run item 14: what the run covered, in place of
 * "Updated N fields across M techniques". `techniquesMapped` is the run's
 * applied count (`ai_runs.applied_count`: techniques the AI gave a status to),
 * not the changed ones. "of {total}" shows only when a batch failed, first
 * pass or re-ask (`batchesFailed` is their sum, advisor 6220638526 item 5,
 * A4 option (b)), and the total is the number of techniques the run ASKED
 * about (`techniquesAsked`, #1325: it is on the run result, so a catalog that
 * moved since cannot change it). A run stored before that field has none, and
 * then the total is the MAPPABLE catalog count -- every technique that is not
 * a computed parent, the codes `mitre_map` is asked about -- derived from the
 * catalog, never typed (advisor, #736 comment 6216024281). The workspace
 * renders this only once the catalog has loaded, so the catalog is required.
 */
export function AttackMappingDone({
  toolsAvailable,
  techniquesMapped,
  batchesFailed,
  techniquesAsked,
  catalog,
}: {
  toolsAvailable: number;
  techniquesMapped: number;
  batchesFailed: number;
  /** #1325: the run's own total; null or absent for an older run. */
  techniquesAsked?: number | null;
  catalog: readonly CatalogTechnique[];
}): JSX.Element {
  const n = (k: number) => k.toLocaleString("en-US");
  let across = n(techniquesMapped);
  if (batchesFailed > 0) {
    const parents = new Set(
      catalog.map((t) => t.parent_id).filter((p): p is string => p !== null),
    );
    const mappable = catalog.filter((t) => !parents.has(t.id)).length;
    across = `${across} of ${n(techniquesAsked ?? mappable)}`;
  }
  return (
    <p
      className="text-sm text-ink-secondary"
      aria-live="polite"
      data-testid="attack-mapping-done"
    >
      {`Mapping done for ${n(toolsAvailable)} ${toolsAvailable === 1 ? "tool" : "tools"} across ${across} ATT&CK techniques and sub-techniques.`}
    </p>
  );
}
