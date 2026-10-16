"use client";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import {
  CsfProxyError,
  fetchProfile,
  patchDimensionScore,
} from "@/lib/csf/client";
import {
  CAPPED_NOTE,
  DIMENSION_HINTS,
  HELP_EVIDENCE,
  HELP_IN_SCOPE,
  HELP_LEVEL_BANDS,
  HELP_LEVELS_INTRO,
  HELP_LOCK,
  HELP_SCALE,
  HELP_SUMMARY,
  HELP_TARGET,
  NO_TARGET_NOTE,
  RUBRIC_HEADERS,
  RUBRIC_ROWS,
  type DimKey,
} from "@/lib/csf/editorHelp";
import {
  EVIDENCE_LABEL,
  EVIDENCE_LEVEL_NOTE,
  EVIDENCE_OPTIONS,
  NOTIONAL_FROM_LEVEL,
  levelName,
  notionalCaveat,
} from "@/lib/csf/optionsCopy";
import type {
  CsfDimensionScore,
  CsfDimensionScorePatch,
  CsfEvidenceStatus,
  CsfProfile,
} from "@/lib/csf/types";
import { evidenceStatusOf } from "@/lib/csf/types";

import type { JSX } from "react";

export interface CsfDimensionEditorProps {
  serviceId: string;
  readOnly?: boolean;
  /** Called after any successful edit so the Enterprise roll-up can refresh. */
  onChanged?: () => void;
}

const TIERS: { value: string; label: string }[] = [
  { value: "high", label: "High" },
  { value: "moderate", label: "Moderate" },
  { value: "low", label: "Low" },
];

const DIMS: { key: DimKey; label: string }[] = [
  { key: "governance", label: "Governance" },
  { key: "policy", label: "Policy & Process" },
  { key: "implementation", label: "Implementation" },
  { key: "monitoring", label: "Monitoring & Measurement" },
  { key: "improvement", label: "Continuous Improvement" },
];

/**
 * C-2 (#1056): the scoring instructions, collapsed by default. A native
 * `<details>` so it is keyboard- and screen-reader-operable with no state.
 * The copy and what it rests on live in `@/lib/csf/editorHelp`.
 */
function HowToScore(): JSX.Element {
  return (
    <details className="rounded-md border border-border-subtle bg-surface-sunken px-3 py-2 text-sm">
      <summary className="cursor-pointer font-semibold text-ink-primary">
        {HELP_SUMMARY}
      </summary>
      <div
        className="mt-2 flex flex-col gap-2 text-ink-secondary"
        data-testid="csf-editor-help"
      >
        <p>{HELP_SCALE}</p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                {RUBRIC_HEADERS.map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="border border-border-subtle px-2 py-1 text-left font-semibold text-ink-primary"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {RUBRIC_ROWS.map(([label, zero, one, two]) => (
                <tr key={label}>
                  <th
                    scope="row"
                    className="border border-border-subtle px-2 py-1 text-left font-semibold text-ink-primary"
                  >
                    {label}
                  </th>
                  <td className="border border-border-subtle px-2 py-1">
                    {zero}
                  </td>
                  <td className="border border-border-subtle px-2 py-1">
                    {one}
                  </td>
                  <td className="border border-border-subtle px-2 py-1">
                    {two}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>{HELP_LEVELS_INTRO}</p>
        <ul className="list-disc pl-5">
          {HELP_LEVEL_BANDS.map((band) => (
            <li key={band}>{band}</li>
          ))}
        </ul>
        <p>{HELP_EVIDENCE}</p>
        <p>{HELP_TARGET}</p>
        <p>{HELP_IN_SCOPE}</p>
        <p>{HELP_LOCK}</p>
      </div>
    </details>
  );
}

/** C6 and E2 (#736 6205956728): the level line's note for the row's
 * evidence value, and the notional caveat for a Managed or Optimized level
 * with neither. */
function EvidenceLevelNote({
  row,
}: {
  row: CsfDimensionScore;
}): JSX.Element | null {
  const status = evidenceStatusOf(row);
  const note = EVIDENCE_LEVEL_NOTE[status];
  const notional = status === "neither" && row.level >= NOTIONAL_FROM_LEVEL;
  if (!note && !notional) return null;
  return (
    <>
      {note ? (
        <span
          className="ml-2 text-ink-tertiary"
          data-testid="csf-level-evidence"
        >
          {note}
        </span>
      ) : null}
      {notional ? (
        <span
          className="mt-1 block text-xs text-status-warning-fg"
          data-testid="csf-level-notional"
        >
          {notionalCaveat(row.level)}
        </span>
      ) : null}
    </>
  );
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

export function CsfDimensionEditor({
  serviceId,
  readOnly = false,
  onChanged,
}: CsfDimensionEditorProps): JSX.Element {
  const [tier, setTier] = React.useState("high");
  const [profile, setProfile] = React.useState<CsfProfile | null>(null);
  const [code, setCode] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const hintIdPrefix = React.useId();

  const loadTier = React.useCallback(
    async (t: string) => {
      try {
        const p = await fetchProfile(serviceId, t);
        setProfile(p);
        setCode((prev) =>
          prev && p.rows.some((r) => r.subcategory_code === prev)
            ? prev
            : (p.rows[0]?.subcategory_code ?? null),
        );
      } catch (err) {
        setError(describeError(err));
      }
    },
    [serviceId],
  );

  React.useEffect(() => {
    void (async () => {
      await loadTier(tier);
    })();
  }, [tier, loadTier]);

  const row = profile?.rows.find((r) => r.subcategory_code === code) ?? null;

  async function apply(patch: CsfDimensionScorePatch): Promise<void> {
    if (!row) return;
    setBusy(true);
    setError(null);
    try {
      const next = await patchDimensionScore(row.id, patch);
      setProfile((prev) =>
        prev
          ? {
              ...prev,
              rows: prev.rows.map((r) => (r.id === next.id ? next : r)),
            }
          : prev,
      );
      onChanged?.();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Edit dimension scores</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        {error ? (
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        ) : null}

        <HowToScore />

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1" role="tablist" aria-label="Tier">
            {TIERS.map((t) => (
              <button
                key={t.value}
                type="button"
                role="tab"
                aria-selected={tier === t.value}
                onClick={() => setTier(t.value)}
                className={[
                  "rounded-md border px-3 py-1.5 text-xs font-semibold",
                  tier === t.value
                    ? "border-brand-500 bg-brand-500 text-ink-on-accent"
                    : "border-border bg-surface-card text-ink-secondary hover:bg-surface-sunken",
                ].join(" ")}
              >
                {t.label}
              </button>
            ))}
          </div>
          <select
            aria-label="Subcategory"
            value={code ?? ""}
            onChange={(e) => setCode(e.target.value)}
            className="rounded-md border border-border bg-surface-card px-2 py-1.5 text-sm text-ink-primary"
          >
            {(profile?.rows ?? []).map((r) => (
              <option key={r.id} value={r.subcategory_code}>
                {r.subcategory_code}
              </option>
            ))}
          </select>
        </div>

        {!row ? (
          <p className="text-sm text-ink-tertiary">Select a subcategory.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {DIMS.map((d) => (
              <div
                key={d.key}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <div className="flex flex-col">
                  <span className="text-sm text-ink-secondary">{d.label}</span>
                  <span
                    id={`${hintIdPrefix}-${d.key}`}
                    className="text-xs text-ink-tertiary"
                  >
                    {DIMENSION_HINTS[d.key]}
                  </span>
                </div>
                <div
                  className="flex gap-1"
                  role="radiogroup"
                  aria-label={d.label}
                  aria-describedby={`${hintIdPrefix}-${d.key}`}
                >
                  {[0, 1, 2].map((v) => {
                    const active = row[d.key] === v;
                    return (
                      <button
                        key={v}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        disabled={readOnly || busy}
                        onClick={() => void apply({ [d.key]: v })}
                        className={[
                          "h-8 w-8 rounded-md border text-sm font-semibold",
                          active
                            ? "border-brand-500 bg-brand-500 text-ink-on-accent"
                            : "border-border bg-surface-card text-ink-secondary hover:bg-surface-sunken",
                          readOnly || busy
                            ? "cursor-not-allowed opacity-60"
                            : "",
                        ].join(" ")}
                      >
                        {v}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-3 text-sm">
              <span className="text-ink-secondary">
                Total{" "}
                <span className="font-semibold text-ink-primary">
                  {row.total}
                </span>{" "}
                · Level{" "}
                <span
                  className="font-semibold text-ink-primary"
                  data-testid="csf-level-name"
                >
                  {levelName(row.level)}
                </span>
                {/* Only an assessment approved before Option 3 (rules 1 or
                    2) is still capped, and keeps saying so. Every other
                    row's level is the scores' alone, and C6 and E2 (#736
                    6205956728) say what its evidence value means. */}
                {row.evidence_capped ? (
                  <>
                    <span className="ml-2 text-status-warning-fg">
                      (capped — no evidence)
                    </span>
                    <span className="mt-1 block text-xs text-status-warning-fg">
                      {CAPPED_NOTE}
                    </span>
                  </>
                ) : (
                  <EvidenceLevelNote row={row} />
                )}
              </span>
              <label className="flex items-center gap-2">
                <span className="text-ink-secondary">Target</span>
                <select
                  value={row.target_level ?? ""}
                  disabled={readOnly || busy}
                  onChange={(e) =>
                    void apply({
                      target_level: e.target.value
                        ? Number(e.target.value)
                        : null,
                    })
                  }
                  className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                >
                  <option value="">—</option>
                  {[1, 2, 3, 4, 5].map((l) => (
                    <option key={l} value={l}>
                      {levelName(l)}
                    </option>
                  ))}
                </select>
              </label>
              {row.target_level === null ? (
                <p className="w-full text-right text-xs text-ink-tertiary">
                  {NO_TARGET_NOTE}
                </p>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-4 text-sm">
              {/* E1 (migration 0074): three values. None changes the
                  scores or the level except under a frozen assessment's cap. */}
              <label className="flex items-center gap-2">
                <span className="text-ink-secondary">{EVIDENCE_LABEL}</span>
                {/* aria-label: a select inside its label would otherwise
                    take the selected option's text into its name. */}
                <select
                  aria-label={EVIDENCE_LABEL}
                  value={evidenceStatusOf(row)}
                  disabled={readOnly || busy}
                  onChange={(e) =>
                    void apply({
                      evidence_status: e.currentTarget
                        .value as CsfEvidenceStatus,
                    })
                  }
                  className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                >
                  {EVIDENCE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={row.in_scope}
                  disabled={readOnly || busy}
                  onChange={(e) =>
                    void apply({ in_scope: e.currentTarget.checked })
                  }
                />
                <span className="text-ink-secondary">In scope</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={row.locked}
                  disabled={readOnly || busy}
                  onChange={(e) =>
                    void apply({ locked: e.currentTarget.checked })
                  }
                />
                <span className="text-ink-secondary">Lock vs AI reruns</span>
              </label>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
