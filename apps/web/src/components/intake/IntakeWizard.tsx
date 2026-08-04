"use client";
import { useSession } from "next-auth/react";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import { fetchIntake, ProxyError, submitIntake } from "@/lib/intake/client";
import { SelectClientPrompt } from "@/components/site/SelectClientPrompt";
import {
  WIZARD_STEPS,
  type ClientProfilePatch,
  type CsfProfile,
  type IntakePatchRequest,
  type IntakeStateResponse,
  type ServiceRequestInput,
  type ServiceType,
  type WizardStepKey,
} from "@/lib/intake/types";

import { IntakeProgress } from "./IntakeProgress";
import { IntakeSubmitted } from "./IntakeSubmitted";
import { SaveStatus } from "./SaveStatus";
import { Step1Services } from "./steps/Step1Services";
import { Step2Organization } from "./steps/Step2Organization";
import { Step3Contact } from "./steps/Step3Contact";
import { Step4Systems } from "./steps/Step4Systems";
import { Step5Notes } from "./steps/Step5Notes";
import { Step6Review } from "./steps/Step6Review";
import { useIntakeAutoSave } from "./useIntakeAutoSave";

import type { JSX } from "react";

const STEP_INDEX: Record<WizardStepKey, number> = WIZARD_STEPS.reduce(
  (acc, step, i) => {
    acc[step.key] = i;
    return acc;
  },
  {} as Record<WizardStepKey, number>,
);

export function IntakeWizard(): JSX.Element {
  const session = useSession();
  const [state, setState] = React.useState<IntakeStateResponse | null>(null);
  const [step, setStep] = React.useState<WizardStepKey>("services");
  const [completed, setCompleted] = React.useState<Set<WizardStepKey>>(
    new Set(),
  );
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [needsClient, setNeedsClient] = React.useState(false);

  const [serviceInputs, setServiceInputs] = React.useState<
    Record<ServiceType, ServiceRequestInput>
  >({} as Record<ServiceType, ServiceRequestInput>);

  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const [submitted, setSubmitted] = React.useState(false);

  const autoSave = useIntakeAutoSave((next) => setState(next));

  React.useEffect(() => {
    let cancelled = false;
    fetchIntake()
      .then((s) => {
        if (cancelled) return;
        setState(s);
        // Hydrate per-service inputs from any existing requests so re-edits
        // keep notes/deadline/targets (and so target validation passes after
        // a reload of an in-progress intake).
        const inputs = {} as Record<ServiceType, ServiceRequestInput>;
        for (const sr of s.service_requests) {
          inputs[sr.service_type] = {
            service_type: sr.service_type,
            notes: sr.notes ?? undefined,
            deadline: sr.deadline ?? undefined,
            csf_target_tier: sr.csf_target_tier ?? undefined,
            csf_profile: (sr.csf_profile as CsfProfile | null) ?? undefined,
            zt_target_stage: sr.zt_target_stage ?? undefined,
          };
        }
        setServiceInputs(inputs);
        if (s.intake_completed_at) setStep("review");
      })
      .catch((err) => {
        if (cancelled) return;
        // Admin with no active client selected: the backend returns
        // 400 "X-Client-Id required". Show a friendly picker prompt instead.
        if (err instanceof ProxyError && err.status === 400) {
          setNeedsClient(true);
          return;
        }
        setLoadError(
          err instanceof Error ? err.message : "Failed to load intake.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function goPrev(): void {
    const idx = STEP_INDEX[step] ?? 0;
    if (idx <= 0) return;
    setStep(WIZARD_STEPS[idx - 1].key);
  }

  function goNext(): void {
    const idx = STEP_INDEX[step] ?? 0;
    setCompleted((prev) => {
      const next = new Set(prev);
      next.add(step);
      return next;
    });
    if (idx >= WIZARD_STEPS.length - 1) return;
    setStep(WIZARD_STEPS[idx + 1].key);
  }

  function onServicesChange(services: ServiceType[]): void {
    void autoSave.save({ client: { service_interests: services } });
  }

  function onClientFieldChange(patch: ClientProfilePatch): void {
    void autoSave.save({ client: patch });
  }

  function onProfileFieldChange(patch: IntakePatchRequest): void {
    void autoSave.save(patch);
  }

  function onSystemsChange(prompting_context: string): void {
    void autoSave.save({
      client: { prompting_context: prompting_context || undefined },
    });
  }

  async function onSubmit(): Promise<void> {
    if (!state?.client) return;
    setSubmitting(true);
    setSubmitError(null);
    const picks = (state.client.service_interests ?? []) as ServiceType[];
    const requests = picks.map((svc) => ({
      ...(serviceInputs[svc] ?? { service_type: svc }),
      service_type: svc,
    }));
    try {
      const next = await submitIntake({
        client: {
          legal_name: state.client.legal_name,
          dba_name: state.client.dba_name ?? undefined,
          website: state.client.website ?? undefined,
          size_band: state.client.size_band ?? undefined,
          industry: state.client.industry ?? undefined,
          address_line1: state.client.address_line1 ?? undefined,
          address_line2: state.client.address_line2 ?? undefined,
          city: state.client.city ?? undefined,
          state: state.client.state ?? undefined,
          postal_code: state.client.postal_code ?? undefined,
          country: state.client.country ?? undefined,
          prompting_context: state.client.prompting_context ?? undefined,
          service_interests: picks,
        },
        service_requests: requests,
      });
      setState(next);
      setSubmitted(true);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Failed to submit intake.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const isFirst = STEP_INDEX[step] === 0;
  const isLast = STEP_INDEX[step] === WIZARD_STEPS.length - 1;

  if (needsClient) {
    return <SelectClientPrompt action="start the intake" />;
  }

  if (loadError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Couldn&apos;t load your intake</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-status-danger-fg">{loadError}</p>
        </CardBody>
      </Card>
    );
  }

  if (submitted && state) {
    return <IntakeSubmitted state={state} />;
  }

  const userEmail = session.data?.user?.email ?? null;
  const userName = session.data?.user?.name ?? null;

  return (
    <div className="flex flex-col gap-6">
      <IntakeProgress currentStep={step} completed={completed} />
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle>
              {WIZARD_STEPS.find((s) => s.key === step)?.label}
            </CardTitle>
            <SaveStatus state={autoSave.saveState} />
          </div>
        </CardHeader>
        <CardBody>
          {!state ? (
            <p className="text-sm text-ink-tertiary">Loading your intake…</p>
          ) : step === "services" ? (
            <Step1Services state={state} onSave={onServicesChange} />
          ) : step === "organization" ? (
            <Step2Organization state={state} onSave={onClientFieldChange} />
          ) : step === "contact" ? (
            <Step3Contact
              defaults={{
                display_name: userName,
                title: null,
                phone: null,
                timezone: null,
                email: userEmail,
              }}
              onSave={onProfileFieldChange}
            />
          ) : step === "systems" ? (
            <Step4Systems state={state} onSave={onSystemsChange} />
          ) : step === "notes" ? (
            <Step5Notes
              state={state}
              serviceInputs={serviceInputs}
              onChange={setServiceInputs}
            />
          ) : (
            <Step6Review
              state={state}
              serviceInputs={serviceInputs}
              submitting={submitting}
              submitError={submitError}
              alreadySubmittedAt={state.intake_completed_at}
              onSubmit={onSubmit}
            />
          )}
        </CardBody>
      </Card>
      <footer className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={goPrev}
          disabled={isFirst}
          className="rounded-md border border-border bg-surface-card px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken disabled:cursor-not-allowed disabled:opacity-60"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={goNext}
          disabled={isLast}
          className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Next →
        </button>
      </footer>
    </div>
  );
}
