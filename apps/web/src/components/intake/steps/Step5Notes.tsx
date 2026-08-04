"use client";
import * as React from "react";

import { Field, inputClasses, textareaClasses } from "../Field";
import { Dropzone, EmptyArtifactsHint } from "../Dropzone";
import { RedactionDisclosure } from "../RedactionDisclosure";
import { type ArtifactSummary, listArtifacts } from "@/lib/intake/artifacts";
import {
  CSF_PROFILES,
  CSF_TARGET_TIERS,
  SERVICE_LABELS,
  ZT_TARGET_STAGES,
  type CsfProfile,
  type IntakeStateResponse,
  type ServiceRequestInput,
  type ServiceType,
} from "@/lib/intake/types";

import type { JSX } from "react";

export interface Step5NotesProps {
  state: IntakeStateResponse;
  serviceInputs: Record<ServiceType, ServiceRequestInput>;
  onChange: (next: Record<ServiceType, ServiceRequestInput>) => void;
}

/**
 * Stage-4 baseline: per-service notes + deadline live in the wizard's local
 * state and are bundled into POST /intake/submit. We don't PATCH partial
 * service_request rows on this step — the API only writes them at final
 * submit.
 *
 * Stage-6 addition: document upload + redaction disclosure render at the
 * top of this step. Artifacts hit POST /artifacts directly (separate from
 * the intake state); the upload list reloads each time the user lands here.
 */
export function Step5Notes({
  state,
  serviceInputs,
  onChange,
}: Step5NotesProps): JSX.Element {
  const picks = (state.client?.service_interests ?? []) as ServiceType[];

  const [artifacts, setArtifacts] = React.useState<ArtifactSummary[]>([]);
  const [listError, setListError] = React.useState<string | null>(null);

  const refreshArtifacts = React.useCallback(async () => {
    try {
      const res = await listArtifacts();
      setArtifacts(res.items);
      setListError(null);
    } catch (err) {
      setListError(
        err instanceof Error ? err.message : "Failed to load uploads.",
      );
    }
  }, []);

  React.useEffect(() => {
    void (async () => {
      await refreshArtifacts();
    })();
  }, [refreshArtifacts]);

  function update(svc: ServiceType, patch: Partial<ServiceRequestInput>): void {
    onChange({
      ...serviceInputs,
      [svc]: {
        ...serviceInputs[svc],
        service_type: svc,
        ...patch,
      },
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="uploads-heading"
        className="flex flex-col gap-3"
      >
        <h3
          id="uploads-heading"
          className="text-sm font-semibold uppercase tracking-wider text-ink-tertiary"
        >
          Supporting documents
        </h3>
        <RedactionDisclosure />
        <Dropzone
          onUploaded={(a) => {
            setArtifacts((prev) => [a, ...prev]);
          }}
        />
        {listError ? (
          <p className="text-xs text-status-danger-fg" role="alert">
            {listError}
          </p>
        ) : null}
        {artifacts.length === 0 ? (
          <EmptyArtifactsHint />
        ) : (
          <ul aria-label="Uploaded artifacts" className="flex flex-col gap-1">
            {artifacts.map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-surface-card px-3 py-2 text-sm"
              >
                <span
                  className="truncate font-medium text-ink-primary"
                  title={a.title}
                >
                  {a.title}
                </span>
                <span className="shrink-0 text-xs text-ink-tertiary">
                  {(a.size_bytes / 1024).toFixed(1)} KB · {a.mime_type}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section
        aria-labelledby="service-notes-heading"
        className="flex flex-col gap-3"
      >
        <h3
          id="service-notes-heading"
          className="text-sm font-semibold uppercase tracking-wider text-ink-tertiary"
        >
          Per-service notes
        </h3>
        {picks.length === 0 ? (
          <p className="text-sm text-ink-secondary">
            You haven&apos;t picked any services yet. Go back to step 1 to
            choose at least one.
          </p>
        ) : (
          <p className="text-sm text-ink-secondary">
            Add notes or target deadlines for each service. These ride along
            when you submit; you can refine them in the assessment workspace
            afterwards.
          </p>
        )}
        {picks.map((svc) => {
          const input = serviceInputs[svc] ?? { service_type: svc };
          return (
            <section
              key={svc}
              aria-labelledby={`svc-${svc}-heading`}
              className="rounded-md border border-border-subtle bg-surface-card p-4"
            >
              <h4
                id={`svc-${svc}-heading`}
                className="text-sm font-semibold text-ink-primary"
              >
                {SERVICE_LABELS[svc]}
              </h4>
              {svc === "nist_csf" ||
              svc === "zero_trust_cisa" ||
              svc === "zero_trust_dod" ? (
                <div className="mt-3 rounded-md border border-border-subtle bg-surface-sunken p-3">
                  <p className="text-xs font-semibold uppercase tracking-wider text-brand-500">
                    Assessment target — required
                  </p>
                  <p className="mt-1 text-xs text-ink-secondary">
                    Tell us the maturity you&apos;re aiming for. Your consultant
                    validates this rather than scoring it from scratch.
                  </p>
                  <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {svc === "nist_csf" ? (
                      <>
                        <Field
                          id={`svc-${svc}-tier`}
                          label="Target maturity tier *"
                        >
                          <select
                            id={`svc-${svc}-tier`}
                            value={input.csf_target_tier ?? ""}
                            onChange={(e) =>
                              update(svc, {
                                csf_target_tier: e.target.value
                                  ? Number(e.target.value)
                                  : undefined,
                              })
                            }
                            className={inputClasses}
                          >
                            <option value="">Select a tier…</option>
                            {CSF_TARGET_TIERS.map((t) => (
                              <option key={t.value} value={t.value}>
                                {t.label}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <Field
                          id={`svc-${svc}-profile`}
                          label="CSF profile *"
                          hint="FIPS-199 impact band."
                        >
                          <select
                            id={`svc-${svc}-profile`}
                            value={input.csf_profile ?? ""}
                            onChange={(e) =>
                              update(svc, {
                                csf_profile: e.target.value
                                  ? (e.target.value as CsfProfile)
                                  : undefined,
                              })
                            }
                            className={inputClasses}
                          >
                            <option value="">Select a profile…</option>
                            {CSF_PROFILES.map((p) => (
                              <option key={p.value} value={p.value}>
                                {p.label}
                              </option>
                            ))}
                          </select>
                        </Field>
                      </>
                    ) : (
                      <Field
                        id={`svc-${svc}-stage`}
                        label="Target maturity stage *"
                      >
                        <select
                          id={`svc-${svc}-stage`}
                          value={input.zt_target_stage ?? ""}
                          onChange={(e) =>
                            update(svc, {
                              zt_target_stage: e.target.value
                                ? Number(e.target.value)
                                : undefined,
                            })
                          }
                          className={inputClasses}
                        >
                          <option value="">Select a stage…</option>
                          {ZT_TARGET_STAGES[svc].map((s) => (
                            <option key={s.value} value={s.value}>
                              {s.label}
                            </option>
                          ))}
                        </select>
                      </Field>
                    )}
                  </div>
                </div>
              ) : null}
              <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field
                  id={`svc-${svc}-notes`}
                  label="Notes"
                  className="sm:col-span-2"
                >
                  <textarea
                    id={`svc-${svc}-notes`}
                    defaultValue={input.notes ?? ""}
                    onBlur={(e) =>
                      update(svc, { notes: e.target.value || undefined })
                    }
                    className={textareaClasses}
                    rows={3}
                  />
                </Field>
                <Field
                  id={`svc-${svc}-deadline`}
                  label="Target deadline"
                  hint="Optional. ISO date."
                >
                  <input
                    id={`svc-${svc}-deadline`}
                    type="date"
                    defaultValue={input.deadline?.slice(0, 10) ?? ""}
                    onBlur={(e) =>
                      update(svc, {
                        deadline: e.target.value
                          ? new Date(e.target.value).toISOString()
                          : undefined,
                      })
                    }
                    className={inputClasses}
                  />
                </Field>
              </div>
            </section>
          );
        })}
      </section>
    </div>
  );
}
