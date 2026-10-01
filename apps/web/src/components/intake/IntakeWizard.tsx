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
import { clientFacingError } from "@/lib/describe-save-error";

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

  // #252: the client fields as this person last ENTERED them, from every save
  // this page has sent. The server's copy (`state.client`) changes only when a
  // save's answer arrives, so it lags an in-flight save, keeps the old value
  // after a failed or unanswered one (#550), and can end on an older value
  // when two answers land out of order. Submit and the steps read
  // `viewState`, the server's copy with these entries laid over it, so what
  // is shown and sent is what was typed. A key sent as `undefined` is left
  // out, because JSON drops it and the server never saw it.
  const [enteredClient, setEnteredClient] = React.useState<ClientProfilePatch>(
    {},
  );
  const viewState = React.useMemo<IntakeStateResponse | null>(
    () =>
      state && state.client
        ? { ...state, client: { ...state.client, ...enteredClient } }
        : state,
    [state, enteredClient],
  );

  function saveEntered(patch: IntakePatchRequest): void {
    const entered = Object.fromEntries(
      Object.entries(patch.client ?? {}).filter(([, v]) => v !== undefined),
    ) as ClientProfilePatch;
    if (Object.keys(entered).length > 0) {
      setEnteredClient((prev) => ({ ...prev, ...entered }));
    }
    void autoSave.save(patch);
  }

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
        setLoadError(clientFacingError(err, "Failed to load intake."));
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
    saveEntered({ client: { service_interests: services } });
  }

  function onClientFieldChange(patch: ClientProfilePatch): void {
    saveEntered({ client: patch });
  }

  function onProfileFieldChange(patch: IntakePatchRequest): void {
    saveEntered(patch);
  }

  function onSystemsChange(prompting_context: string): void {
    saveEntered({
      client: { prompting_context: prompting_context || undefined },
    });
  }

  async function onSubmit(): Promise<void> {
    const client = viewState?.client;
    if (!client) return;
    setSubmitting(true);
    setSubmitError(null);
    const picks = (client.service_interests ?? []) as ServiceType[];
    const requests = picks.map((svc) => ({
      ...(serviceInputs[svc] ?? { service_type: svc }),
      service_type: svc,
    }));
    try {
      const next = await submitIntake({
        client: {
          // `?? undefined` like every sibling field below. Since D-080 an
          // unnamed org is NULL rather than a sentinel, and submitting one is
          // refused by the API with a typed 422 ("Organization legal name is
          // required to submit intake.") — the wizard does not pre-empt that
          // check, so the user gets the server's message rather than a silent
          // no-op.
          legal_name: client.legal_name ?? undefined,
          dba_name: client.dba_name ?? undefined,
          website: client.website ?? undefined,
          size_band: client.size_band ?? undefined,
          industry: client.industry ?? undefined,
          address_line1: client.address_line1 ?? undefined,
          address_line2: client.address_line2 ?? undefined,
          city: client.city ?? undefined,
          state: client.state ?? undefined,
          postal_code: client.postal_code ?? undefined,
          country: client.country ?? undefined,
          prompting_context: client.prompting_context ?? undefined,
          service_interests: picks,
        },
        service_requests: requests,
      });
      setState(next);
      // What was entered is now what the server holds; read its copy again.
      setEnteredClient({});
      setSubmitted(true);
    } catch (err) {
      setSubmitError(clientFacingError(err, "Failed to submit intake."));
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
          {!viewState ? (
            <p className="text-sm text-ink-tertiary">Loading your intake…</p>
          ) : step === "services" ? (
            <Step1Services state={viewState} onSave={onServicesChange} />
          ) : step === "organization" ? (
            <Step2Organization state={viewState} onSave={onClientFieldChange} />
          ) : step === "contact" ? (
            <Step3Contact
              // Read what the API actually returns. These were hardcoded nulls,
              // so a title or phone typed here came back blank on the next
              // visit even though it had saved (UX finding 9).
              defaults={{
                display_name: viewState.contact?.display_name ?? userName,
                title: viewState.contact?.title ?? null,
                phone: viewState.contact?.phone ?? null,
                timezone: viewState.contact?.timezone ?? null,
                email: userEmail,
              }}
              override={{
                primary_contact_name:
                  viewState.client?.primary_contact_name ?? null,
                primary_contact_email:
                  viewState.client?.primary_contact_email ?? null,
                primary_contact_title:
                  viewState.client?.primary_contact_title ?? null,
                primary_contact_phone:
                  viewState.client?.primary_contact_phone ?? null,
              }}
              onSave={onProfileFieldChange}
            />
          ) : step === "systems" ? (
            <Step4Systems state={viewState} onSave={onSystemsChange} />
          ) : step === "notes" ? (
            <Step5Notes
              state={viewState}
              serviceInputs={serviceInputs}
              onChange={setServiceInputs}
            />
          ) : (
            <Step6Review
              state={viewState}
              serviceInputs={serviceInputs}
              submitting={submitting}
              savesInFlight={autoSave.savesInFlight}
              submitError={submitError}
              alreadySubmittedAt={viewState.intake_completed_at}
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
