import type { JSX } from "react";

import type { CatalogTechnique } from "@/lib/attack/types";

/**
 * #1182, Gene's 2026-10-15 test-run item 14: what the run covered, in place of
 * "Updated N fields across M techniques". `techniquesMapped` is the run's
 * applied count (`ai_runs.applied_count`: techniques the AI gave a status to),
 * not the changed ones. "of {total}" shows only when a batch failed, and the
 * total is the MAPPABLE catalog count -- every technique that is not a
 * computed parent, the codes `mitre_map` is asked about -- derived from the
 * catalog, never typed (advisor, #736 comment 6216024281). On a partial run
 * the line waits for the catalog rather than read as a complete run.
 */
export function AttackMappingDone({
  toolsAvailable,
  techniquesMapped,
  batchesFailed,
  catalog,
}: {
  toolsAvailable: number;
  techniquesMapped: number;
  batchesFailed: number;
  catalog: readonly CatalogTechnique[] | null;
}): JSX.Element | null {
  const n = (k: number) => k.toLocaleString("en-US");
  let across = n(techniquesMapped);
  if (batchesFailed > 0) {
    if (catalog === null) return null;
    const parents = new Set(
      catalog.map((t) => t.parent_id).filter((p): p is string => p !== null),
    );
    const mappable = catalog.filter((t) => !parents.has(t.id)).length;
    across = `${across} of ${n(mappable)}`;
  }
  return (
    <p
      className="text-sm text-ink-secondary"
      aria-live="polite"
      data-testid="attack-mapping-done"
    >
      {`Mapping done for ${n(toolsAvailable)} tools across ${across} ATT&CK techniques and sub-techniques.`}
    </p>
  );
}
