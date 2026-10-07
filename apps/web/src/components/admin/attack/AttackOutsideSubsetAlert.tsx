import type { JSX } from "react";

import type {
  AttackAssessment,
  AttackOutsideCitation,
  AttackToolField,
} from "@/lib/attack/types";

/**
 * #851: rows that credit a tool outside the client's CURRENT security tool
 * list. The copy is the advisor's (#736): S1, S2 and S3b on a draft, which
 * approve refuses until each is removed; S5 once approved, when nothing can
 * change the rows and release only discloses. Every string approved, including
 * the "not in" wording and the singulars (#736, 18:56Z and 6024072042).
 */
const LABEL: Record<AttackToolField, string> = {
  detection_tools: "Detection",
  prevention_tools: "Prevention",
  response_tools: "Response",
};

function rowCount(items: AttackOutsideCitation[]): number {
  return new Set(items.map((o) => o.technique_code)).size;
}

function lead(n: number, approved: boolean): string {
  if (approved) {
    return n === 1
      ? "1 technique row in this approved assessment credits a tool that is not in the client's security tool list. The deliverable counts that tool."
      : `${n} technique rows in this approved assessment credit a tool that is not in the client's security tool list. The deliverable counts that tool.`;
  }
  return n === 1
    ? "1 technique row credits a tool that is not in the client's security tool list, so its status may count a tool the client does not use:"
    : `${n} technique rows credit a tool that is not in the client's security tool list, so their status may count a tool the client does not use:`;
}

export function AttackOutsideSubsetAlert({
  assessment,
  phase,
}: {
  assessment: AttackAssessment;
  /** Which instance this is: the draft's (step 2) or the approved one's (step 3). */
  phase: "draft" | "approved";
}): JSX.Element | null {
  const items = assessment.citations_outside_subset ?? [];
  const approved = assessment.status !== "draft";
  if (approved !== (phase === "approved")) return null;
  if (assessment.subset_checked === false) {
    // The third state: nothing is listed because nothing could be checked.
    return (
      <p
        role="status"
        data-testid="attack-outside-subset-not-checked"
        className="rounded-md border border-line bg-surface-sunken p-3 text-sm text-ink-secondary"
      >
        The tools cited here were not checked against a security tool list,
        because the client has none.
      </p>
    );
  }
  if (items.length === 0) return null;
  return (
    <div
      role="status"
      data-testid="attack-outside-subset"
      className="flex flex-col gap-1 rounded-md border border-status-warning-fg/40 bg-surface-sunken p-3 text-sm text-status-warning-fg"
    >
      <p>{lead(rowCount(items), approved)}</p>
      <ul className="list-disc pl-5">
        {items.map((o) => (
          <li key={`${o.technique_code}|${o.field}|${o.tool}`}>
            {`${o.technique_code}, ${LABEL[o.field]}: ${o.tool}`}
            {o.locked ? " (locked, so Run AI will not change it)" : ""}
          </li>
        ))}
      </ul>
      {approved ? null : (
        <p>
          Remove the tool in the technique&apos;s panel, or unlock the row and
          use Run AI.
        </p>
      )}
    </div>
  );
}
