"use client";

import * as React from "react";

import { StatusPill } from "@shield/design-system";

import { AttackProxyError, fetchAttackAiInputs } from "@/lib/attack/client";
import type {
  AttackAiInputCapability,
  AttackAiInputSourceList,
  AttackAiInputs,
} from "@/lib/attack/types";

import type { JSX } from "react";

/**
 * What this mapping will run against — and, the part nothing answered before,
 * what it will NOT.
 *
 * The workspace reported a single number, `23 tools available`, and only after
 * the run had finished. `_client_capability_membership` applies three
 * load-bearing filters — security scope, list status, approved-snapshot
 * membership — and every one of them is correct and invisible. That is the
 * defect: a `gap` on a client deliverable can mean "no control here" or "the
 * tool was filtered and nobody could see it", and nothing in the product told a
 * consultant which. A run with ZERO capabilities wrote 607 fabricated gaps
 * across 633 techniques on 2026-08-07 (N-033) and looked like a posture
 * finding.
 *
 * NOT a second payload view. `AiPreviewButton`, immediately beside this, shows
 * the redacted payload that WILL be sent. This shows what was dropped on the
 * way to it, unredacted, because an admin cannot recognise a redacted tool
 * name.
 *
 * Loads on mount rather than behind a click. The failure mode is a drop nobody
 * looked for, and a disclosure behind a button is one an admin who does not
 * suspect a problem never opens. The route is read-only, constructs no
 * provider, writes no `llm_calls` row and carries no rate limit, so a page view
 * costs nothing. It never gates Run AI; the typed 409 in the API is the only
 * guard.
 *
 * THE ONE THING THIS COMPONENT MUST NOT DO is render an unknowable count as a
 * number. `excluded_attribution` is a tri-state because
 * `Reconciliation.attribution_complete` is not persisted, so an empty
 * `excluded_rows` is the stored form of BOTH "nothing was excluded" and
 * "attribution failed". A "0 rows dropped" over the second is the persuasive
 * kind of silent under-report — a number, in a provenance view, that a
 * consultant would reasonably act on — inside the panel built to end silent
 * drops. Every path below that could reach for `?? 0` says the words instead.
 *
 * WHY THIS DIFFERS FROM `AttackHeatmapCard`, which DOES use `?? 0` (at :69,
 * :100, :102) and is correct to. There the field is `pending_review: int = 0`
 * -- additive and server-defaulted under the C0 pattern, so an absent value
 * genuinely means zero, and `AttackHeatmapCard.test.tsx:53` rightly asserts
 * that absence means nothing was withheld.
 *
 * Here the field is a TRI-STATE, and two of its three values mean the
 * opposite of zero: `not_recorded` and `unknown` both mean WE CANNOT KNOW.
 * Only `complete` licenses a digit. So `?? 0` is right there and wrong here,
 * and the difference is in the field's shape rather than in house style.
 *
 * Written down because the inconsistency is the kind someone reconciles
 * later -- and reconciling it in this direction puts the silent under-report
 * back.
 */

/**
 * Explicit phases. A single `inputs: T | null` would make "still loading" and
 * "the request failed" the same value, and the renderer would then have to
 * guess — the shape CLAUDE.md records as failing open the moment the box is
 * slow.
 */
type Phase =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; inputs: AttackAiInputs };

function describeError(err: unknown): string {
  if (err instanceof AttackProxyError) {
    const payload = err.payload as
      | { error?: { message?: string }; detail?: { message?: string } }
      | undefined;
    const message = payload?.error?.message ?? payload?.detail?.message;
    if (message) {
      return message;
    }
    return `Couldn't load what this mapping will use (HTTP ${err.status}).`;
  }
  return "Couldn't load what this mapping will use.";
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/**
 * What a source list may honestly say about rows dropped at extraction.
 *
 * Three returns for three states, and none of them is a bare zero. `unknown`
 * deliberately produces no digit at all: there is no number to round, hedge or
 * caveat, because the stored bytes do not contain one.
 */
function describeAttribution(list: AttackAiInputSourceList): {
  label: string;
  tone: "neutral" | "warning" | "info";
  title: string;
} {
  switch (list.excluded_attribution) {
    case "complete":
      return {
        label: `${list.excluded_rows_named} named`,
        tone: "neutral",
        title:
          "The reconciliation balanced, so every dropped row is named and listed below.",
      };
    case "unknown":
      return {
        label: "Not knowable",
        tone: "warning",
        title:
          "A reconciliation ran but its per-row half was not stored. Nothing was recorded either way, so this is NOT zero — it is unknown.",
      };
    case "not_recorded":
      return {
        label: "Not recorded",
        tone: "info",
        title:
          "No reconciliation was stored for this list, so there is no claim to make either way. Usually that means it predates the extraction record — but a seeded or hand-built list stores nothing either, and the two are indistinguishable here.",
      };
  }
}

/**
 * A capability whose snapshot entry outlived its live row keeps its name and
 * vendor and loses everything descriptive. Rendering those cells as "—" would
 * say "uncategorised" where the truth is "we cannot look" — the same
 * conflation, one row down, that the tri-state above exists to refuse.
 */
function describeCell(
  capability: AttackAiInputCapability,
  value: string | null,
): string {
  if (capability.live_row_missing) {
    return "not readable";
  }
  return value && value.length > 0 ? value : "—";
}

export function AttackAiInputsPanel({
  serviceId,
}: {
  serviceId: string;
}): JSX.Element {
  // The phase is stored WITH the service it describes, and the effective phase
  // is derived rather than reset in the effect. Resetting it there is both a
  // `react-hooks/set-state-in-effect` error and a cascading render; the reason
  // to care is that between the prop change and the reset there is one render
  // in which service B's panel shows service A's provenance. On a surface whose
  // entire job is saying which tools feed WHICH mapping, a stale-but-plausible
  // answer is worse than a spinner.
  const [loaded, setLoaded] = React.useState<{
    serviceId: string;
    phase: Phase;
  }>({ serviceId, phase: { kind: "loading" } });
  const phase: Phase =
    loaded.serviceId === serviceId ? loaded.phase : { kind: "loading" };

  React.useEffect(() => {
    let cancelled = false;
    fetchAttackAiInputs(serviceId)
      .then((inputs) => {
        if (!cancelled) {
          setLoaded({ serviceId, phase: { kind: "ready", inputs } });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoaded({
            serviceId,
            phase: { kind: "error", message: describeError(err) },
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [serviceId]);

  if (phase.kind === "loading") {
    return (
      <p
        className="text-sm text-ink-tertiary"
        aria-live="polite"
        data-testid="attack-ai-inputs-loading"
      >
        Checking what this mapping will use…
      </p>
    );
  }

  if (phase.kind === "error") {
    // FAIL LOUDLY. A panel that quietly vanished would read as "nothing was
    // dropped", which is the exact misreading this component exists to prevent.
    return (
      <p
        className="text-sm text-status-danger-fg"
        role="alert"
        data-testid="attack-ai-inputs-error"
      >
        {phase.message}
      </p>
    );
  }

  const { capabilities, not_sent, excluded, sources, totals } = phase.inputs;
  const liveRowMissing = capabilities.filter((c) => c.live_row_missing).length;
  // No backend total exists for these three, so they are derived here. The
  // counts that DO have one — sent, not_sent, awaiting_signoff, the two
  // withheld reasons, excluded_rows_named, lists_with_unknown_exclusions — are
  // read from `totals` rather than re-counted, so the panel and the API cannot
  // disagree about them.
  const notRecordedLists = sources.filter(
    (s) => s.excluded_attribution === "not_recorded",
  ).length;
  const staleLists = sources.filter((s) => s.membership_stale).length;
  const supersededLists = sources.filter(
    (s) => !s.is_latest_for_service,
  ).length;

  return (
    <div
      className="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-sunken p-3"
      data-testid="attack-ai-inputs"
    >
      {sources.length === 0 ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="attack-ai-inputs-no-lists"
        >
          No Tech Debt capability list feeds this mapping. Every technique would
          be reported as a gap, and that would be an artifact of no inventory
          being loaded rather than a finding about this client.
        </p>
      ) : totals.sent === 0 ? (
        <p
          className="text-sm font-medium text-status-warning-fg"
          data-testid="attack-ai-inputs-none-sent"
        >
          No security capabilities will be sent — every technique would be
          reported as a gap. {totals.not_sent}{" "}
          {plural(totals.not_sent, "capability is", "capabilities are")} on the
          contributing {plural(sources.length, "list", "lists")} and{" "}
          {plural(totals.not_sent, "was", "were")} filtered out; the breakdown
          is below.
        </p>
      ) : (
        <p className="text-sm font-medium text-ink-primary">
          Mapping against{" "}
          <span data-testid="attack-ai-inputs-sent">{totals.sent}</span>{" "}
          security {plural(totals.sent, "capability", "capabilities")} from{" "}
          {sources.length} Tech Debt {plural(sources.length, "list", "lists")}.
        </p>
      )}

      {/* Rendered whenever there are lists, including when nothing was
          withheld. A line that only appears on a bad run is one whose absence
          reads as zero — and "zero withheld" is a claim the panel is entitled
          to make, unlike the extraction tri-state below. */}
      {sources.length > 0 ? (
        <p
          className="text-sm text-ink-secondary"
          data-testid="attack-ai-inputs-not-sent"
        >
          {totals.not_sent === 0 ? (
            <>
              Nothing on those lists was withheld: every named capability is
              being offered to the model.
            </>
          ) : (
            <>
              <span className="font-semibold text-ink-primary">
                {totals.not_sent}
              </span>{" "}
              named {plural(totals.not_sent, "capability", "capabilities")} on
              those lists {plural(totals.not_sent, "is", "are")} NOT offered to
              the model
              {totals.withheld_security_scope > 0
                ? ` — ${totals.withheld_security_scope} ruled out of the security subset`
                : ""}
              {totals.withheld_not_in_approved_snapshot > 0
                ? `${totals.withheld_security_scope > 0 ? "," : " —"} ${
                    totals.withheld_not_in_approved_snapshot
                  } absent from the membership frozen at approval`
                : ""}
              . The model cannot cite {plural(totals.not_sent, "it", "them")},
              so a technique{" "}
              {plural(totals.not_sent, "it covers", "they cover")} will read as
              a gap.
            </>
          )}
        </p>
      ) : null}

      {/* The tri-state, in prose. No branch here prints a zero for `unknown`,
          and none may ever be added. */}
      {sources.length > 0 ? (
        <p
          className="text-sm text-ink-secondary"
          data-testid="attack-ai-inputs-excluded"
        >
          Uploaded rows that never became a capability at all:{" "}
          <span className="font-semibold text-ink-primary">
            {totals.excluded_rows_named}
          </span>{" "}
          named.
          {totals.lists_with_unknown_exclusions > 0 ? (
            <span
              className="text-status-warning-fg"
              data-testid="attack-ai-inputs-excluded-unknown"
            >
              {" "}
              {totals.lists_with_unknown_exclusions} of the {sources.length}{" "}
              {plural(sources.length, "list", "lists")} cannot say what{" "}
              {plural(totals.lists_with_unknown_exclusions, "it", "they")}{" "}
              dropped: the extraction record does not distinguish &ldquo;nothing
              was excluded&rdquo; from &ldquo;we could not tell&rdquo;, so the
              real total is <em>at least</em> {totals.excluded_rows_named} and
              is not knowable from what was stored. Re-running the extraction
              does not help: a clean run that excluded nothing stores the same
              empty record as a run whose attribution failed, so it would land
              here again at the cost of a live AI call.
            </span>
          ) : null}
          {notRecordedLists > 0 ? (
            <span data-testid="attack-ai-inputs-excluded-not-recorded">
              {" "}
              {notRecordedLists}{" "}
              {plural(notRecordedLists, "list predates", "lists predate")} the
              extraction record and {plural(notRecordedLists, "makes", "make")}{" "}
              no claim either way.
            </span>
          ) : null}
          {totals.lists_with_unknown_exclusions === 0 &&
          notRecordedLists === 0 ? (
            <span> Every source row is accounted for.</span>
          ) : null}
        </p>
      ) : null}

      {totals.awaiting_signoff > 0 ||
      totals.sent_without_source_document > 0 ||
      liveRowMissing > 0 ||
      staleLists > 0 ||
      supersededLists > 0 ? (
        <div className="flex flex-wrap gap-2">
          {totals.awaiting_signoff > 0 ? (
            <StatusPill tone="warning">
              {totals.awaiting_signoff} awaiting security sign-off
            </StatusPill>
          ) : null}
          {staleLists > 0 ? (
            <StatusPill tone="warning">
              {staleLists} approved{" "}
              {plural(staleLists, "snapshot", "snapshots")} out of date
            </StatusPill>
          ) : null}
          {liveRowMissing > 0 ? (
            <StatusPill tone="warning">
              {liveRowMissing} sent from a deleted row
            </StatusPill>
          ) : null}
          {totals.sent_without_source_document > 0 ? (
            <StatusPill tone="neutral">
              {totals.sent_without_source_document} with no source document
            </StatusPill>
          ) : null}
          {supersededLists > 0 ? (
            <StatusPill tone="info">
              Includes {supersededLists} superseded{" "}
              {plural(supersededLists, "version", "versions")}
            </StatusPill>
          ) : null}
        </div>
      ) : null}

      {staleLists > 0 ? (
        <p
          className="text-xs text-status-warning-fg"
          data-testid="attack-ai-inputs-stale"
        >
          An approved list&rsquo;s frozen membership no longer matches the
          current security classification, so what the model may cite is what
          the list looked like at approval — not what it looks like now.
          Re-approve the capability list in its Tech Debt workspace; that is the
          one audited way to move it.
        </p>
      ) : null}

      {supersededLists > 0 ? (
        <p className="text-xs text-ink-secondary">
          Every non-discarded capability list counts, superseded versions
          included — a tool removed in a later version is still offered to the
          model. Discard a list in its Tech Debt workspace to take it out.
        </p>
      ) : null}

      {sources.length > 0 ? (
        <details data-testid="attack-ai-inputs-sources">
          <summary className="cursor-pointer text-sm font-medium text-brand-600 hover:text-brand-500">
            Show {sources.length} source{" "}
            {plural(sources.length, "list", "lists")}
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left text-sm">
              <caption className="sr-only">
                Every Tech Debt capability list feeding this ATT&amp;CK mapping,
                what it contributed, and what it dropped
              </caption>
              <thead className="text-xs uppercase tracking-wide text-ink-tertiary">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    List
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Status
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Membership
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Sent
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Withheld
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    Rows dropped at extraction
                  </th>
                </tr>
              </thead>
              <tbody>
                {sources.map((list) => {
                  const attribution = describeAttribution(list);
                  return (
                    <tr
                      key={list.capability_list_id}
                      className="border-t border-border-subtle"
                    >
                      <th
                        scope="row"
                        className="py-1 pr-3 font-medium text-ink-primary"
                      >
                        {list.tech_debt_service_title} v{list.version}
                        {list.is_latest_for_service ? "" : " (superseded)"}
                      </th>
                      <td className="py-1 pr-3 text-ink-secondary">
                        {list.status}
                      </td>
                      <td className="py-1 pr-3 text-ink-secondary">
                        {list.membership_from_snapshot
                          ? `frozen at approval${
                              list.membership_stale ? " — out of date" : ""
                            }`
                          : "live rows"}
                      </td>
                      <td className="py-1 pr-3 text-ink-secondary">
                        {list.sent_count}
                      </td>
                      <td className="py-1 pr-3 text-ink-secondary">
                        {list.not_sent_count}
                      </td>
                      <td
                        className="py-1 text-ink-secondary"
                        title={attribution.title}
                        data-testid={`attack-ai-inputs-attribution-${list.capability_list_id}`}
                      >
                        <StatusPill tone={attribution.tone}>
                          {attribution.label}
                        </StatusPill>
                        {list.source_rows_total !== null ? (
                          <span className="ml-2 text-xs text-ink-tertiary">
                            of {list.source_rows_total} uploaded
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}

      {not_sent.length > 0 ? (
        <details data-testid="attack-ai-inputs-not-sent-table">
          <summary className="cursor-pointer text-sm font-medium text-brand-600 hover:text-brand-500">
            Show {not_sent.length} withheld{" "}
            {plural(not_sent.length, "capability", "capabilities")}
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <caption className="sr-only">
                Named capabilities the ATT&amp;CK mapping will not be offered,
                and why
              </caption>
              <thead className="text-xs uppercase tracking-wide text-ink-tertiary">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Capability
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Vendor
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Why it is not offered
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    From
                  </th>
                </tr>
              </thead>
              <tbody>
                {not_sent.map((item, i) => (
                  <tr
                    key={`${item.capability_list_id}-${item.name}-${i}`}
                    className="border-t border-border-subtle"
                  >
                    <th
                      scope="row"
                      className="py-1 pr-3 font-medium text-ink-primary"
                    >
                      {item.name}
                    </th>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {item.vendor ?? "—"}
                    </td>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {item.reason === "security_scope"
                        ? "Ruled out of the security subset — the model called it non-security and a consultant agreed."
                        : "Absent from the membership frozen when the list was approved. It was either added or reclassified into scope afterwards, and nothing on record separates those. Re-approve the list to include it."}
                    </td>
                    <td className="py-1 text-ink-secondary">
                      {item.source_document
                        ? item.source_document.title
                        : "no source document"}
                      {item.source_list_version !== null
                        ? ` (v${item.source_list_version})`
                        : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}

      {excluded.length > 0 ? (
        <details data-testid="attack-ai-inputs-excluded-table">
          <summary className="cursor-pointer text-sm font-medium text-brand-600 hover:text-brand-500">
            Show {excluded.length} uploaded{" "}
            {plural(excluded.length, "row", "rows")} that produced no capability
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-sm text-ink-secondary">
            {excluded.map((row) => (
              <li key={`${row.capability_list_id}-${row.index}`}>
                <span className="text-ink-tertiary">Row {row.index}:</span>{" "}
                {row.summary}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {capabilities.length > 0 ? (
        <details data-testid="attack-ai-inputs-table">
          <summary className="cursor-pointer text-sm font-medium text-brand-600 hover:text-brand-500">
            Show all {capabilities.length}{" "}
            {plural(capabilities.length, "capability", "capabilities")} being
            sent
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <caption className="sr-only">
                Every security capability being offered to the ATT&amp;CK
                mapping, and the document it came from
              </caption>
              <thead className="text-xs uppercase tracking-wide text-ink-tertiary">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Capability
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Vendor
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Category
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Security functions
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    Source document
                  </th>
                </tr>
              </thead>
              <tbody>
                {capabilities.map((item, i) => (
                  <tr
                    key={`${item.capability_list_id}-${item.name}-${i}`}
                    className="border-t border-border-subtle"
                  >
                    <th
                      scope="row"
                      className="py-1 pr-3 font-medium text-ink-primary"
                    >
                      {item.name}
                      {item.awaiting_signoff ? (
                        <span className="ml-2 text-xs font-normal text-status-warning-fg">
                          awaiting sign-off
                        </span>
                      ) : null}
                      {item.live_row_missing ? (
                        <span
                          className="ml-2 text-xs font-normal text-status-warning-fg"
                          data-testid="attack-ai-inputs-live-row-missing"
                        >
                          live row deleted — still citable under this name, but
                          nothing about it can be read
                        </span>
                      ) : null}
                    </th>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {item.vendor ?? "—"}
                    </td>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {describeCell(item, item.category)}
                    </td>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {describeCell(
                        item,
                        item.security_functions.join(", ") || null,
                      )}
                    </td>
                    <td className="py-1 text-ink-secondary">
                      {item.source_document
                        ? `${item.source_document.title}${
                            item.source_list_version !== null
                              ? ` (v${item.source_list_version})`
                              : ""
                          }`
                        : describeCell(item, null)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </div>
  );
}
