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
  SERVICE_DESCRIPTIONS,
  SERVICE_LABELS,
  type IntakeStateResponse,
  type ServiceType,
} from "@/lib/intake/types";

import type { JSX } from "react";

export interface Step1ServicesProps {
  state: IntakeStateResponse;
  onSave: (services: ServiceType[]) => void;
}

const SERVICE_ORDER: ServiceType[] = [
  "tech_debt",
  "zero_trust_cisa",
  "zero_trust_dod",
  "nist_csf",
  "attack_coverage",
  "consultation",
];

export function Step1Services({
  state,
  onSave,
}: Step1ServicesProps): JSX.Element {
  const selected = new Set<ServiceType>(
    (state.client?.service_interests ?? []) as ServiceType[],
  );

  function toggle(service: ServiceType): void {
    const next = new Set(selected);
    if (next.has(service)) {
      next.delete(service);
    } else {
      // "I'm not sure" is exclusive with the four real services.
      if (service === "consultation") {
        next.clear();
        next.add(service);
      } else {
        next.delete("consultation");
        next.add(service);
      }
    }
    onSave(Array.from(next));
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-secondary">
        Pick the services you want this assessment to cover. You can change this
        anytime before submitting.
      </p>
      <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <legend className="sr-only">Service selection</legend>
        {SERVICE_ORDER.map((service) => {
          const isOn = selected.has(service);
          const isConsultation = service === "consultation";
          return (
            <Card
              key={service}
              className={
                isOn ? "border-border-focus ring-1 ring-border-focus" : ""
              }
            >
              <CardHeader>
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={isOn}
                    onChange={() => toggle(service)}
                    className="mt-1 h-4 w-4 rounded-sm border-border text-brand-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-border-focus"
                    aria-describedby={`svc-${service}-desc`}
                  />
                  <span className="flex flex-col">
                    <CardTitle>{SERVICE_LABELS[service]}</CardTitle>
                    {isConsultation ? (
                      <CardDescription>
                        Not ready to pick a service? Start with a consultation —
                        a Kentro consultant will reach out.
                      </CardDescription>
                    ) : null}
                  </span>
                </label>
              </CardHeader>
              <CardBody>
                <p
                  id={`svc-${service}-desc`}
                  className="text-sm text-ink-secondary"
                >
                  {SERVICE_DESCRIPTIONS[service]}
                  {/* Wizard mechanics, not a property of the service — so this
                      stays here rather than in the shared description. */}
                  {service === "consultation"
                    ? " Selecting this clears the other picks."
                    : ""}
                </p>
              </CardBody>
            </Card>
          );
        })}
      </fieldset>
    </div>
  );
}
