import type { JSX } from "react";

import type { ZtDroppedSuggestion, ZtRunAiResponse } from "@/lib/zt/types";

/**
 * Run-AI accounting for the Zero Trust workspace (W1, issue #44, D-047).
 *
 * Mirrors `CsfPlaybookPanel`'s `RunAiAccounting` with ZT's vocabulary: no
 * `wrong_type` (every value ZT applies is a stage), plus `protected` for an
 * offline run declining to overwrite a non-AI answer.
 *
 * Its own file rather than inline in `ZtWorkspace`, so the drop branches can be
 * tested directly. Reaching them through the workspace needs the whole client
 * mocked, and fixture mode cannot produce a VALIDATION drop — the fixture emits
 * the parser's own keys with in-range values by construction.
 *
 * One exception, found in round 2 and worth stating because the blanket claim
 * "fixture mode cannot produce a drop" is FALSE for ZT: `protected` is
 * fixture-ONLY. `protected_keys` returns an empty set off-fixture
 * (`app/ai/provenance.py`), so that reason can never occur live and DOES occur
 * offline whenever the run touches a client-submitted or consultant-typed row.
 */

const DROP_REASON_LABEL: Record<ZtDroppedSuggestion["reason"], string> = {
  // About the capability lookup, not the catalogue: a code can be well-formed
  // and still match no seeded row.
  unknown_key: "no matching capability (is that code spelled right?)",
  unknown_field: "field name this run does not recognize",
  entry_shape: "could not be read as a suggestion",
  // Not "was not a number": `1.9` and `true` are refused here too, and both are
  // numbers in the sense a reader means. What is required is a whole stage.
  unparseable: "value was not a whole number",
  out_of_range: "value fell outside the framework's stage range",
  superseded: "overwritten by a later suggestion for the same field",
  locked: "row is locked",
  protected: "answer was not written by the AI, and an offline run left it",
};

/**
 * Reasons that are the system working as designed, not a failure.
 *
 * An allow-list, named, so adding a reason server-side is a deliberate choice
 * about which side it belongs on — anything unlisted lands in the red alert.
 * `protected` sits here beside `locked`: both are by-design skips, but they are
 * NOT merged into one label, because telling a consultant a row is "locked"
 * when nobody locked it is a false statement about who did what.
 */
const BY_DESIGN_SKIPS: ReadonlySet<string> = new Set(["locked", "protected"]);

/**
 * Reasons that mean "we did not understand this", not "we lost a value you
 * asked for". A model volunteering a rationale or a confidence per capability
 * has lost nothing, but every one of those keys is an `unknown_field`. Routing
 * them into the red alert prints a failure over a run in which everything asked
 * for was applied — the #31 trap. Visible, not red.
 */
const NOT_UNDERSTOOD: ReadonlySet<string> = new Set(["unknown_field"]);

/** At most this many items per reason, then a count of the rest. */
const ITEM_CAP = 10;

function describeReason(reason: string): string {
  // The payload is JSON, so `reason` is only a union by convention. An unmapped
  // code must show as itself — an empty bullet reads as "no reason given".
  return (
    DROP_REASON_LABEL[reason as ZtDroppedSuggestion["reason"]] ??
    `unrecognized reason "${reason}"`
  );
}

function describeItem(d: ZtDroppedSuggestion): string {
  const where = d.key ?? "(no capability named)";
  const what = d.field ? `${where} ${d.field}` : where;
  // The model's own output, bounded server-side and carried for exactly one
  // purpose: a human reading it. Without it "out of range" is unactionable —
  // the consultant cannot tell a model that wrote `9` from one that wrote
  // `"high"`.
  const sent =
    d.value === null || d.value === undefined ? "" : ` = ${String(d.value)}`;
  const many = d.values > 1 ? ` (${d.values} values)` : "";
  return `${what}${sent}${many}`;
}

function groupByReason(
  items: ZtDroppedSuggestion[],
): [string, ZtDroppedSuggestion[]][] {
  const by = new Map<string, ZtDroppedSuggestion[]>();
  for (const d of items) {
    const list = by.get(d.reason);
    if (list) list.push(d);
    else by.set(d.reason, [d]);
  }
  return [...by.entries()];
}

function summarizeItems(items: ZtDroppedSuggestion[]): string {
  const shown = items.slice(0, ITEM_CAP).map(describeItem).join(", ");
  const rest = items.length - ITEM_CAP;
  // "records", not a bare count: every other number here is in VALUES, and one
  // record can stand for several.
  return rest > 0 ? `${shown}, and ${rest} more records` : shown;
}

export function ZtRunAiAccounting({
  result,
}: {
  result: ZtRunAiResponse;
}): JSX.Element {
  const dropped = result.dropped ?? [];
  const skipped = dropped.filter((d) => BY_DESIGN_SKIPS.has(d.reason));
  const unrecognized = dropped.filter((d) => NOT_UNDERSTOOD.has(d.reason));
  const failed = dropped.filter(
    (d) => !BY_DESIGN_SKIPS.has(d.reason) && !NOT_UNDERSTOOD.has(d.reason),
  );
  const sumValues = (xs: ZtDroppedSuggestion[]): number =>
    xs.reduce((n, d) => n + d.values, 0);
  const failedValues = sumValues(failed);
  const unrecognizedValues = sumValues(unrecognized);
  const changedRows = new Set(result.changed.map((c) => c.capability_code))
    .size;

  // A run that received NOTHING is not a clean run. The response parsed, so no
  // error path fired, and "applied 0 of 0" reads as calmly as "applied 12 of
  // 12" — the most reassuring possible way to report a wholly-lost response.
  if (result.suggestions_received === 0) {
    return (
      <p className="text-sm text-status-danger-fg" role="alert">
        The AI returned no suggestions at all, so nothing was applied. That is
        expected only if the model genuinely had nothing to say — otherwise its
        response did not match the shape this job expects. Re-run, and if it
        repeats, the prompt and the parser have drifted apart.
      </p>
    );
  }

  return (
    // No aria-live on the wrapper: the failure block is a role="alert"
    // (implicitly assertive), and nesting it in a polite region makes some
    // screen readers announce it twice.
    <div className="space-y-2">
      <p className="text-sm text-ink-secondary" aria-live="polite">
        AI applied{" "}
        <span className="font-semibold text-ink-primary">
          {result.suggestions_applied}
        </span>{" "}
        of {result.suggestions_received} suggested value
        {result.suggestions_received === 1 ? "" : "s"}, changing{" "}
        {result.changed.length} field
        {result.changed.length === 1 ? "" : "s"} across {changedRows} capabilit
        {changedRows === 1 ? "y" : "ies"}.
      </p>

      {failed.length > 0 ? (
        <div className="text-sm text-status-danger-fg" role="alert">
          <p className="font-semibold">
            {failedValues > 0
              ? `${failedValues} suggested value${failedValues === 1 ? "" : "s"} could not be applied:`
              : // A failure record can legitimately account for zero values —
                // "this capability does not exist" is a fault about the row,
                // and the values it carried are counted under the name they
                // arrived with. "0 could not be applied" over a red alert reads
                // as a contradiction and invites dismissing it.
                "Some suggestions could not be applied:"}
          </p>
          <ul className="list-disc pl-5">
            {groupByReason(failed).map(([reason, items]) => (
              <li key={reason}>
                {describeReason(reason)} — {summarizeItems(items)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {unrecognized.length > 0 ? (
        <div className="text-sm text-ink-secondary">
          <p>
            {unrecognizedValues} value{unrecognizedValues === 1 ? "" : "s"} came
            back under {unrecognized.length === 1 ? "a name" : "names"} this run
            does not recognize. These are part of the shortfall in the line
            above — not extra. Harmless only if the model volunteered detail
            nobody asked for; if{" "}
            {unrecognized.length === 1 ? "this name is" : "these names are"} a
            stage field spelled differently, the prompt and the parser have
            drifted apart and those stages are lost:
          </p>
          <ul className="list-disc pl-5">
            {unrecognized.slice(0, ITEM_CAP).map((d, i) => (
              <li key={`${d.key ?? ""}-${d.field ?? ""}-${i}`}>
                {describeItem(d)}
              </li>
            ))}
            {unrecognized.length > ITEM_CAP ? (
              <li>and {unrecognized.length - ITEM_CAP} more records</li>
            ) : null}
          </ul>
        </div>
      ) : null}

      {skipped.length > 0 ? (
        // Grouped by reason rather than summed into one number: `locked` and
        // `protected` are different facts about who decided, and the fuller
        // explanation of `protected` is the preserved-answers paragraph below.
        <ul className="list-disc pl-5 text-sm text-ink-tertiary">
          {groupByReason(skipped).map(([reason, items]) => (
            <li key={reason}>
              {/* A skip record can legitimately account for zero values: the
                  row fault is named while its values are counted under the
                  names they arrived with. "0 suggested values skipped" reads as
                  a contradiction, the same way it did in the failure block
                  above. Reachable in live mode only — field-name drift on a
                  locked or protected row — which is why fixture-backed tests
                  could never surface it. */}
              {sumValues(items) > 0
                ? `${sumValues(items)} suggested value${sumValues(items) === 1 ? "" : "s"} skipped`
                : "Suggestions skipped"}{" "}
              — {describeReason(reason)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
