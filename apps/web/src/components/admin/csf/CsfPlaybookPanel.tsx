"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  DataTable,
  type DataTableColumn,
} from "@shield/design-system";

import {
  CsfProxyError,
  exportPlaybook,
  fetchEnterpriseProfile,
  runCsfAi,
  seedProfiles,
} from "@/lib/csf/client";

import { AiPreviewButton } from "../AiPreviewButton";
import { RunAiGuard } from "../RunAiGuard";
import { CsfDimensionEditor } from "./CsfDimensionEditor";
import { CsfGapActionEditor } from "./CsfGapActionEditor";
import type {
  CsfDroppedSuggestion,
  CsfPlaybookExport,
  CsfRunAiResponse,
  EnterpriseProfile,
  EnterpriseSubcategory,
} from "@/lib/csf/types";

import type { JSX } from "react";

export interface CsfPlaybookPanelProps {
  serviceId: string;
  readOnly?: boolean;
}

function describeError(err: unknown): string {
  if (err instanceof CsfProxyError) {
    const payload = err.payload as
      { error?: { message?: string }; detail?: string } | undefined;
    return (
      payload?.error?.message ??
      payload?.detail ??
      `Request failed (${err.status}).`
    );
  }
  return err instanceof Error ? err.message : "Request failed.";
}

const DROP_REASON_LABEL: Record<CsfDroppedSuggestion["reason"], string> = {
  // Deliberately about the ROW, not the subcategory: the lookup is on
  // tier + subcategory_code, and an unseeded tier misses on a code that IS in
  // the catalogue. "not in the catalogue" sent readers hunting a catalogue bug.
  // No em dash inside a label — the list separator is already an em dash, and a
  // second one made the key read as the end of the sentence.
  unknown_key:
    "no matching row (is that tier seeded, and the code spelled right?)",
  unknown_field: "field name this run does not recognize",
  entry_shape: "could not be read as a suggestion",
  // Not "was not a number": `1.9` and `true` are refused here too, and both are
  // numbers in the sense a reader means. What is required is a whole 0/1/2.
  unparseable: "value was not a whole number",
  out_of_range: "value fell outside 0–2",
  wrong_type: "narrative came back as something other than text",
  superseded: "overwritten by a later suggestion for the same field",
  locked: "row is locked",
};

/**
 * Reasons that are the system working as designed, not a failure.
 *
 * An allow-list, named, so that adding a reason server-side is a deliberate
 * choice about which side it belongs on. Written as `!== "locked"` this was a
 * deny-list of one string: any future by-design skip would have landed in the
 * red "could not be applied" alert and rebuilt the #31 alert-fatigue problem.
 * (Hardening — with today's vocabulary the two forms behave identically.)
 */
const BY_DESIGN_SKIPS: ReadonlySet<string> = new Set(["locked"]);

/**
 * Reasons that mean "we did not understand this", not "we lost a value you
 * asked for".
 *
 * A model that volunteers an extra key per row — a confidence, a rationale —
 * has lost nothing, but every one of those keys is an `unknown_field`. Routing
 * them into the red alert would print "318 suggested values could not be
 * applied" over a run in which everything asked for was applied: a wrong number
 * on a normal run, which is the #31 trap and PR #39's rule at once. They stay
 * visible, because a misnamed dimension is indistinguishable from a harmless
 * annotation and the drift signal is the whole point — just not in red.
 */
const NOT_UNDERSTOOD: ReadonlySet<string> = new Set(["unknown_field"]);

function describeReason(reason: string): string {
  // The payload is JSON, so `reason` is only a union by convention. An unmapped
  // code must show as itself — an empty bullet reads as "no reason given".
  return (
    DROP_REASON_LABEL[reason as CsfDroppedSuggestion["reason"]] ??
    `unrecognized reason "${reason}"`
  );
}

function describeItem(d: CsfDroppedSuggestion): string {
  const where = d.key ?? "(no subcategory named)";
  // `field` is what distinguishes two drops on the same row; without it a row
  // with two bad dimensions rendered as the same key printed twice. `values` is
  // shown when one record stands for several, so a reader counting bullets
  // cannot get a different total from the headline.
  const what = d.field ? `${where} ${d.field}` : where;
  // The model's own output, bounded server-side. The API carries it verbatim
  // for exactly one purpose — a human reading it — and nothing rendered it, so
  // the panel said a value fell outside 0–2 and never said what it was. That
  // makes "out of range" unactionable: the consultant cannot tell a model that
  // wrote `5` from one that wrote `"high"`.
  const sent =
    d.value === null || d.value === undefined ? "" : ` = ${String(d.value)}`;
  const many = d.values > 1 ? ` (${d.values} values)` : "";
  return `${what}${sent}${many}`;
}

/**
 * At most `ITEM_CAP` items, then a count of the rest.
 *
 * Systematic drift is the expected shape of a real failure here, not the
 * exception: one misnamed dimension over a seeded Playbook is 318 records. Both
 * lists were unbounded, so that run rendered either ~950 bullets or one bullet
 * holding a 5 KB comma-joined string — the diagnostic collapsing at exactly the
 * moment it matters. The total always comes from `values`, never from the
 * number of items shown, so capping the list cannot change a reported number.
 */
const ITEM_CAP = 10;

function summarizeItems(items: CsfDroppedSuggestion[]): string {
  const shown = items.slice(0, ITEM_CAP).map(describeItem).join(", ");
  const rest = items.length - ITEM_CAP;
  // "records", not a bare count: every other number on this panel is in
  // VALUES, and one record can stand for several. "and 15 more" beside bullets
  // reading "(4 values)" invites a reader to add 15 to a value total.
  return rest > 0 ? `${shown}, and ${rest} more records` : shown;
}

function groupByReason(
  dropped: CsfDroppedSuggestion[],
): [string, CsfDroppedSuggestion[]][] {
  const groups = new Map<string, CsfDroppedSuggestion[]>();
  for (const d of dropped) {
    const bucket = groups.get(d.reason);
    if (bucket) bucket.push(d);
    else groups.set(d.reason, [d]);
  }
  return [...groups.entries()];
}

/**
 * What the run did with every suggestion it received (W1, issue #44).
 *
 * The applied/received line renders on EVERY run, including a clean one. A
 * block that only appears when something went wrong teaches the reader that its
 * absence means "nothing was dropped" — and the whole defect family this closes
 * is drops that never announced themselves. An explicit "12 of 12" is the only
 * version of that sentence a reader can actually rely on.
 *
 * Rows a human locked are listed apart from the failures. They are the system
 * working as designed, and issue #31 rejected a warning that fires during
 * normal work: it gets trained away, and takes the real ones with it.
 *
 * SCOPE, stated because the sentence reads like a completeness claim: this
 * accounts for values suggested for SCORING ROWS. The response's top-level
 * `executive_summary` is not counted here and is not persisted by CSF at all
 * (ZT does persist its equivalent) — hence "score values", not "values".
 */
function RunAiAccounting({
  result,
}: {
  result: CsfRunAiResponse;
}): JSX.Element {
  const skipped = result.dropped.filter((d) => BY_DESIGN_SKIPS.has(d.reason));
  const unrecognized = result.dropped.filter((d) =>
    NOT_UNDERSTOOD.has(d.reason),
  );
  const failed = result.dropped.filter(
    (d) => !BY_DESIGN_SKIPS.has(d.reason) && !NOT_UNDERSTOOD.has(d.reason),
  );
  const failedValues = failed.reduce((n, d) => n + d.values, 0);
  const skippedValues = skipped.reduce((n, d) => n + d.values, 0);
  const unrecognizedValues = unrecognized.reduce((n, d) => n + d.values, 0);
  const changedRows = new Set(result.changed.map((c) => c.subcategory_code))
    .size;

  // A run that received NOTHING is not a clean run. The response parsed, so no
  // error path fired, and "applied 0 of 0" reads as calmly as "applied 12 of
  // 12" — the single most reassuring way to report a wholly-lost response. This
  // is the reader-facing half of #46 (a response under the wrong top-level key
  // still yields an empty list); the accounting must not bless it.
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
    // No aria-live on the wrapper: the failure block below is a role="alert"
    // (implicitly assertive), and nesting it inside a polite region makes some
    // screen readers announce it twice.
    <div className="space-y-2">
      <p className="text-sm text-ink-secondary" aria-live="polite">
        AI applied{" "}
        <span className="font-semibold text-ink-primary">
          {result.suggestions_applied}
        </span>{" "}
        of {result.suggestions_received} suggested score value
        {result.suggestions_received === 1 ? "" : "s"}, changing{" "}
        {result.changed.length} field
        {result.changed.length === 1 ? "" : "s"} across {changedRows} subcategor
        {changedRows === 1 ? "y" : "ies"}.
      </p>

      {failed.length > 0 ? (
        <div className="text-sm text-status-danger-fg" role="alert">
          <p className="font-semibold">
            {failedValues > 0
              ? `${failedValues} suggested score value${failedValues === 1 ? "" : "s"} could not be applied:`
              : // A failure record can legitimately account for zero values —
                // "this row does not exist" is a fault about the row, and the
                // values it carried are counted under the name they arrived
                // with. Printing "0 could not be applied" over a red alert
                // reads as a contradiction and invites dismissing it.
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
            dimension spelled differently, the prompt and the parser have
            drifted apart and those scores are lost:
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
        <p className="text-sm text-ink-tertiary">
          {skippedValues} suggested value{skippedValues === 1 ? "" : "s"}{" "}
          skipped because{" "}
          {skipped.length === 1
            ? "you locked that row"
            : "you locked those rows"}
          .
        </p>
      ) : null}
    </div>
  );
}

const PRIORITY_COLOR: Record<string, { bg: string; fg: string }> = {
  P1: { bg: "#fee2e2", fg: "#991b1b" },
  P2: { bg: "#ffedd5", fg: "#9a3412" },
  P3: { bg: "#f1f5f9", fg: "#475569" },
};

function tierLevels(row: EnterpriseSubcategory): string {
  const order: [string, string][] = [
    ["high", "H"],
    ["moderate", "M"],
    ["low", "L"],
  ];
  return order
    .filter(([t]) => row.tier_levels[t] != null)
    .map(([t, abbr]) => `${abbr}${row.tier_levels[t]}`)
    .join("  ");
}

const COLUMNS: DataTableColumn<EnterpriseSubcategory>[] = [
  { key: "code", header: "Subcategory", cell: (r) => r.subcategory_code },
  { key: "name", header: "Outcome", cell: (r) => r.name },
  { key: "tiers", header: "Tiers", cell: (r) => tierLevels(r) },
  {
    key: "ent",
    header: "Enterprise",
    align: "center",
    cell: (r) => `L${r.enterprise_level}`,
  },
  {
    key: "rule",
    header: "Rule",
    align: "center",
    cell: (r) => `#${r.rollup_rule}`,
  },
  {
    key: "target",
    header: "Target",
    align: "center",
    cell: (r) => (r.target_level ? `L${r.target_level}` : "—"),
  },
  {
    key: "priority",
    header: "Gap",
    align: "center",
    cell: (r) => {
      if (!r.gap) return <span className="text-ink-tertiary">—</span>;
      const c = PRIORITY_COLOR[r.priority ?? "P3"] ?? PRIORITY_COLOR.P3;
      return (
        <span
          className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold"
          style={{ backgroundColor: c.bg, color: c.fg }}
        >
          {r.priority ?? "gap"}
        </span>
      );
    },
  },
];

export function CsfPlaybookPanel({
  serviceId,
  readOnly = false,
}: CsfPlaybookPanelProps): JSX.Element {
  const [enterprise, setEnterprise] = React.useState<EnterpriseProfile | null>(
    null,
  );
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState<"seed" | "run" | "export" | null>(
    null,
  );
  const [runResult, setRunResult] = React.useState<CsfRunAiResponse | null>(
    null,
  );
  const [exportResult, setExportResult] =
    React.useState<CsfPlaybookExport | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Monotonic request sequence: only the newest enterprise-profile fetch may
  // write state. Without this, a slow mount-time GET (StrictMode duplicates,
  // next-dev queuing) resolving AFTER a post-edit reload clobbers fresh data
  // with stale data — the same stale-fetch race family as MessageThread (T8).
  const reqSeq = React.useRef(0);

  const reload = React.useCallback(async () => {
    const seq = ++reqSeq.current;
    const ent = await fetchEnterpriseProfile(serviceId);
    if (seq === reqSeq.current) {
      setEnterprise(ent);
      console.debug(
        `[CsfPlaybookPanel] enterprise-profile applied (seq ${seq})`,
      );
    } else {
      console.debug(
        `[CsfPlaybookPanel] discarded stale enterprise-profile response (seq ${seq}, latest ${reqSeq.current})`,
      );
    }
  }, [serviceId]);

  React.useEffect(() => {
    (async () => {
      try {
        await reload();
      } catch (err) {
        setError(describeError(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [reload]);

  async function onSeed(): Promise<void> {
    setBusy("seed");
    setError(null);
    try {
      await seedProfiles(serviceId);
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  async function onRunAi(): Promise<void> {
    setBusy("run");
    setError(null);
    setRunResult(null);
    try {
      setRunResult(await runCsfAi(serviceId));
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  // Reload after a dimension edit. Unlike a bare `void reload()`, this surfaces
  // a failed refresh to the user via setError instead of letting it become a
  // console-only unhandled rejection (FAIL LOUDLY) — matching onSeed/onRunAi.
  async function onDimensionChanged(): Promise<void> {
    setError(null);
    try {
      await reload();
    } catch (err) {
      setError(describeError(err));
    }
  }

  async function onExport(): Promise<void> {
    setBusy("export");
    setError(null);
    try {
      setExportResult(await exportPlaybook(serviceId));
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  const seeded = (enterprise?.subcategories.length ?? 0) > 0;
  const gapCount = enterprise?.subcategories.filter((s) => s.gap).length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Full Playbook — Working Profiles</CardTitle>
          <CardDescription>
            Tiered (HIGH / MODERATE / LOW) five-dimension scoring rolled up to
            one Enterprise level per subcategory via the weighted-floor rules.
            AI suggests the dimensions; code computes every level, the cap, and
            the roll-up.
          </CardDescription>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          {error ? (
            <p className="text-sm text-status-danger-fg" role="alert">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            {!seeded ? (
              <button
                type="button"
                onClick={() => void onSeed()}
                disabled={busy !== null || readOnly}
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === "seed" ? "Seeding…" : "Seed Working Profiles"}
              </button>
            ) : (
              /* Issue 2: warn before producing canned output when offline. */
              <RunAiGuard onProceed={() => void onRunAi()}>
                {({ onClick }) => (
                  <button
                    type="button"
                    onClick={onClick}
                    disabled={busy !== null || readOnly}
                    className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {busy === "run" ? "Running…" : "Run AI (csf_score)"}
                  </button>
                )}
              </RunAiGuard>
            )}
            {seeded ? (
              <button
                type="button"
                onClick={() => void onExport()}
                disabled={busy !== null}
                className="rounded-md border border-border-default px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === "export" ? "Exporting…" : "Export XLSX"}
              </button>
            ) : null}
            {exportResult ? (
              <span className="flex flex-wrap items-center gap-3 text-sm font-medium">
                {exportResult.artifacts.map((a) => (
                  <a
                    key={a.kind}
                    href={`/api/proxy/artifacts/${a.artifact_id}/download`}
                    className="text-brand-500 hover:underline"
                    title={a.filename}
                  >
                    {a.label}
                  </a>
                ))}
              </span>
            ) : null}
            {seeded ? (
              <span className="text-sm text-ink-secondary">
                {enterprise?.tiers_in_use.length ?? 0} tier(s) in use ·{" "}
                <span className="font-semibold text-ink-primary">
                  {gapCount}
                </span>{" "}
                subcategor{gapCount === 1 ? "y" : "ies"} with a gap
              </span>
            ) : null}
          </div>

          {seeded ? (
            <AiPreviewButton serviceId={serviceId} disabled={busy !== null} />
          ) : null}

          {runResult ? <RunAiAccounting result={runResult} /> : null}

          {loading ? (
            <p className="text-sm text-ink-tertiary">Loading…</p>
          ) : seeded ? (
            <DataTable
              columns={COLUMNS}
              rows={enterprise?.subcategories ?? []}
              rowKey={(r) => r.subcategory_code}
            />
          ) : (
            <p className="text-sm text-ink-secondary">
              Seed the Working Profiles to score the ~106 subcategories across
              the tiers your client uses, then Run AI to draft the dimension
              scores.
            </p>
          )}
        </CardBody>
      </Card>
      {seeded ? (
        <CsfDimensionEditor
          serviceId={serviceId}
          readOnly={readOnly}
          onChanged={() => void onDimensionChanged()}
        />
      ) : null}
      {seeded && gapCount > 0 ? (
        <CsfGapActionEditor serviceId={serviceId} readOnly={readOnly} />
      ) : null}
    </div>
  );
}
