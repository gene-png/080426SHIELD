"use client";
import { StatusPill } from "@shield/design-system";

import {
  CSF_PROFILES,
  CSF_TARGET_TIERS,
  hasMissingTargets,
  SERVICE_LABELS,
  ZT_TARGET_STAGES,
  type IntakeStateResponse,
  type ServiceRequestInput,
  type ServiceType,
} from "@/lib/intake/types";

import type { JSX } from "react";

/** Human-readable summary of the client-set targets for a service, if any. */
function targetSummary(
  svc: ServiceType,
  input: ServiceRequestInput | undefined,
): string | null {
  if (svc === "nist_csf") {
    if (!input?.csf_target_tier && !input?.csf_profile) return null;
    const tier = CSF_TARGET_TIERS.find(
      (t) => t.value === input?.csf_target_tier,
    )?.label;
    const profile = CSF_PROFILES.find(
      (p) => p.value === input?.csf_profile,
    )?.label;
    return [tier, profile].filter(Boolean).join(" · ") || null;
  }
  if (svc === "zero_trust_cisa" || svc === "zero_trust_dod") {
    return (
      ZT_TARGET_STAGES[svc].find((s) => s.value === input?.zt_target_stage)
        ?.label ?? null
    );
  }
  return null;
}

export interface Step6ReviewProps {
  state: IntakeStateResponse;
  serviceInputs: Record<ServiceType, ServiceRequestInput>;
  submitting: boolean;
  submitError: string | null;
  alreadySubmittedAt: string | null;
  onSubmit: () => void;
}

function row(label: string, value: string | null | undefined): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-1 border-b border-border-subtle py-3 last:border-b-0 sm:grid-cols-3">
      <dt className="text-sm font-medium text-ink-secondary sm:col-span-1">
        {label}
      </dt>
      <dd className="text-sm text-ink-primary sm:col-span-2">
        {value ? (
          value
        ) : (
          <span className="italic text-ink-tertiary">Not provided</span>
        )}
      </dd>
    </div>
  );
}

export function Step6Review({
  state,
  serviceInputs,
  submitting,
  submitError,
  alreadySubmittedAt,
  onSubmit,
}: Step6ReviewProps): JSX.Element {
  const c = state.client;
  const picks = (c?.service_interests ?? []) as ServiceType[];
  const legalName =
    c?.legal_name && c.legal_name !== "(pending intake)" ? c.legal_name : null;

  const servicesMissingTargets = picks.filter((svc) =>
    hasMissingTargets(svc, serviceInputs[svc]),
  );
  const targetsIncomplete = servicesMissingTargets.length > 0;

  return (
    <div className="flex flex-col gap-6">
      {alreadySubmittedAt ? (
        <div className="rounded-md border border-status-success-border bg-status-success-bg px-4 py-3 text-sm text-status-success-fg">
          Intake was submitted on{" "}
          {new Date(alreadySubmittedAt).toLocaleString()}. You can re-edit
          earlier steps and re-submit; the admin queue will surface the most
          recent version.
        </div>
      ) : null}

      <section
        aria-labelledby="review-org"
        className="rounded-md border border-border-subtle bg-surface-card p-4"
      >
        <h3
          id="review-org"
          className="text-sm font-semibold uppercase tracking-wider text-ink-tertiary"
        >
          Organization
        </h3>
        <dl className="mt-2">
          {row("Legal name", legalName)}
          {row("DBA / Trade name", c?.dba_name)}
          {row("Website", c?.website)}
          {row("Headcount band", c?.size_band)}
          {row("Industry", c?.industry)}
          {row(
            "Address",
            [
              c?.address_line1,
              c?.address_line2,
              c?.city,
              c?.state,
              c?.postal_code,
              c?.country,
            ]
              .filter(Boolean)
              .join(", ") || null,
          )}
        </dl>
      </section>

      <section
        aria-labelledby="review-services"
        className="rounded-md border border-border-subtle bg-surface-card p-4"
      >
        <h3
          id="review-services"
          className="text-sm font-semibold uppercase tracking-wider text-ink-tertiary"
        >
          Services
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {picks.length === 0 ? (
            <span className="text-sm italic text-ink-tertiary">
              No services picked yet.
            </span>
          ) : (
            picks.map((svc) => (
              <StatusPill key={svc} tone="info" withDot>
                {SERVICE_LABELS[svc]}
              </StatusPill>
            ))
          )}
        </div>
        {picks.length > 0 ? (
          <ul className="mt-4 space-y-3">
            {picks.map((svc) => {
              const input = serviceInputs[svc];
              const target = targetSummary(svc, input);
              if (!input?.notes && !input?.deadline && !target) return null;
              return (
                <li key={svc} className="text-sm">
                  <p className="font-medium text-ink-primary">
                    {SERVICE_LABELS[svc]}
                  </p>
                  {target ? (
                    <p className="text-ink-secondary">Target: {target}</p>
                  ) : null}
                  {input?.deadline ? (
                    <p className="text-ink-secondary">
                      Target deadline:{" "}
                      {new Date(input.deadline).toLocaleDateString()}
                    </p>
                  ) : null}
                  {input.notes ? (
                    <p className="whitespace-pre-wrap text-ink-secondary">
                      {input.notes}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>

      <section
        aria-labelledby="review-context"
        className="rounded-md border border-border-subtle bg-surface-card p-4"
      >
        <h3
          id="review-context"
          className="text-sm font-semibold uppercase tracking-wider text-ink-tertiary"
        >
          Systems and context
        </h3>
        <p className="mt-2 whitespace-pre-wrap text-sm text-ink-primary">
          {c?.prompting_context ? (
            c.prompting_context
          ) : (
            <span className="italic text-ink-tertiary">Not provided</span>
          )}
        </p>
      </section>

      {targetsIncomplete ? (
        <div
          role="alert"
          className="rounded-md border border-status-warning-border bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg"
        >
          Set an assessment target for{" "}
          {servicesMissingTargets.map((s) => SERVICE_LABELS[s]).join(", ")} in
          step 5 before submitting.
        </div>
      ) : null}

      {submitError ? (
        <div
          role="alert"
          className="rounded-md border border-status-danger-border bg-status-danger-bg px-4 py-3 text-sm text-status-danger-fg"
        >
          {submitError}
        </div>
      ) : null}

      <button
        type="button"
        onClick={onSubmit}
        disabled={
          submitting || picks.length === 0 || !legalName || targetsIncomplete
        }
        className="self-end rounded-md bg-brand-500 px-5 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting
          ? "Submitting…"
          : alreadySubmittedAt
            ? "Re-submit intake"
            : "Submit intake"}
      </button>
    </div>
  );
}
