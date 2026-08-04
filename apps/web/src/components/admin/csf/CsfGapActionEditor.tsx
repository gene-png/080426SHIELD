"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";

import {
  CsfProxyError,
  fetchGapActions,
  upsertGapAction,
} from "@/lib/csf/client";
import type { CsfGapAction, CsfGapActionUpsert } from "@/lib/csf/types";

import type { JSX } from "react";

export interface CsfGapActionEditorProps {
  serviceId: string;
  readOnly?: boolean;
}

const CHARACTERIZATIONS: { value: string; label: string }[] = [
  { value: "", label: "—" },
  { value: "accept", label: "Accept" },
  { value: "mitigate", label: "Mitigate" },
  { value: "transfer", label: "Transfer" },
  { value: "avoid", label: "Avoid" },
];

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

export function CsfGapActionEditor({
  serviceId,
  readOnly = false,
}: CsfGapActionEditorProps): JSX.Element {
  const [actions, setActions] = React.useState<CsfGapAction[] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  // Monotonic request sequence: only the newest gap-actions fetch may write
  // state, so a slow mount-time GET can't clobber a fresh post-save reload
  // (the same stale-fetch race guarded in CsfPlaybookPanel).
  const reqSeq = React.useRef(0);

  const reload = React.useCallback(async () => {
    const seq = ++reqSeq.current;
    const data = await fetchGapActions(serviceId);
    if (seq === reqSeq.current) {
      setActions(data?.actions ?? []);
      console.debug(`[CsfGapActionEditor] gap-actions applied (seq ${seq})`);
    } else {
      console.debug(
        `[CsfGapActionEditor] discarded stale gap-actions response (seq ${seq}, latest ${reqSeq.current})`,
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

  async function save(code: string, patch: CsfGapActionUpsert): Promise<void> {
    setError(null);
    try {
      const next = await upsertGapAction(serviceId, code, patch);
      setActions((prev) =>
        prev ? prev.map((a) => (a.subcategory_code === code ? next : a)) : prev,
      );
    } catch (err) {
      setError(describeError(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Action plan (POA&amp;M)</CardTitle>
        <CardDescription>
          For each enterprise gap: characterize the risk response, adjust the
          code-computed priority if needed, and record the remediation owner,
          deadline, resources, success criteria, and POA&amp;M reference. Saved
          automatically; included in the exported playbook workbook.
        </CardDescription>
      </CardHeader>
      <CardBody className="flex flex-col gap-4">
        {error ? (
          <p className="text-sm text-status-danger-fg" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="text-sm text-ink-tertiary" aria-live="polite">
            Loading gaps…
          </p>
        ) : !actions || actions.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            No gaps to plan. Score the Working Profiles and set targets to
            surface remediation gaps.
          </p>
        ) : (
          <ul className="flex flex-col gap-4">
            {actions.map((a) => (
              <li
                key={a.subcategory_code}
                data-testid={`gap-action-${a.subcategory_code}`}
                className="rounded-md border border-border-subtle bg-surface-card p-4"
              >
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-mono text-ink-tertiary">
                      {a.subcategory_code}
                    </p>
                    <p className="text-sm font-medium text-ink-primary">
                      {a.name}
                    </p>
                  </div>
                  <span className="text-xs text-ink-tertiary">
                    L{a.enterprise_level}
                    {a.target_level ? ` → target L${a.target_level}` : ""} ·
                    priority{" "}
                    <span className="font-semibold text-ink-primary">
                      {a.effective_priority ?? "—"}
                    </span>
                    {a.priority_override ? " (override)" : ""}
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-ink-secondary">Characterization</span>
                    <select
                      aria-label={`Characterization ${a.subcategory_code}`}
                      value={a.characterization ?? ""}
                      disabled={readOnly}
                      onChange={(e) =>
                        void save(a.subcategory_code, {
                          characterization: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    >
                      {CHARACTERIZATIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-ink-secondary">
                      Priority override
                    </span>
                    <select
                      aria-label={`Priority ${a.subcategory_code}`}
                      value={a.priority_override ?? ""}
                      disabled={readOnly}
                      onChange={(e) =>
                        void save(a.subcategory_code, {
                          priority_override: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    >
                      <option value="">
                        Default ({a.default_priority ?? "—"})
                      </option>
                      <option value="P1">P1</option>
                      <option value="P2">P2</option>
                      <option value="P3">P3</option>
                    </select>
                  </label>

                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-ink-secondary">Owner</span>
                    <input
                      type="text"
                      aria-label={`Owner ${a.subcategory_code}`}
                      defaultValue={a.owner ?? ""}
                      disabled={readOnly}
                      onBlur={(e) =>
                        void save(a.subcategory_code, {
                          owner: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    />
                  </label>

                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-ink-secondary">Deadline</span>
                    <input
                      type="text"
                      aria-label={`Deadline ${a.subcategory_code}`}
                      placeholder="e.g. 2026-09-30 or Q3"
                      defaultValue={a.deadline ?? ""}
                      disabled={readOnly}
                      onBlur={(e) =>
                        void save(a.subcategory_code, {
                          deadline: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    />
                  </label>

                  <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                    <span className="text-ink-secondary">Resources</span>
                    <textarea
                      aria-label={`Resources ${a.subcategory_code}`}
                      defaultValue={a.resources ?? ""}
                      disabled={readOnly}
                      rows={2}
                      onBlur={(e) =>
                        void save(a.subcategory_code, {
                          resources: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    />
                  </label>

                  <label className="flex flex-col gap-1 text-sm sm:col-span-2">
                    <span className="text-ink-secondary">Success criteria</span>
                    <textarea
                      aria-label={`Success criteria ${a.subcategory_code}`}
                      defaultValue={a.success_criteria ?? ""}
                      disabled={readOnly}
                      rows={2}
                      onBlur={(e) =>
                        void save(a.subcategory_code, {
                          success_criteria: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    />
                  </label>

                  <label className="flex flex-col gap-1 text-sm">
                    <span className="text-ink-secondary">
                      POA&amp;M reference
                    </span>
                    <input
                      type="text"
                      aria-label={`POA&M ref ${a.subcategory_code}`}
                      defaultValue={a.poam_ref ?? ""}
                      disabled={readOnly}
                      onBlur={(e) =>
                        void save(a.subcategory_code, {
                          poam_ref: e.currentTarget.value,
                        })
                      }
                      className="rounded-md border border-border bg-surface-card px-2 py-1 text-sm text-ink-primary"
                    />
                  </label>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
