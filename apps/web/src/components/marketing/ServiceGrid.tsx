import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@shield/design-system";

import type { JSX } from "react";

const SERVICES: { title: string; description: string }[] = [
  {
    title: "Technical Debt Review",
    description:
      "Identify overlapping tools, capability gaps, and modernization opportunities across your cybersecurity stack.",
  },
  {
    title: "Zero Trust Assessment",
    description:
      "Measure Zero Trust maturity against CISA ZTMM 2.0 and DoD reference architectures with prioritized implementation roadmaps.",
  },
  {
    title: "NIST CSF 2.0 Assessment",
    description:
      "Assess organizational cybersecurity maturity using NIST CSF 2.0 with weighted scoring, prioritized gaps, and actionable remediation planning.",
  },
  {
    title: "MITRE ATT&CK Coverage Mapping",
    description:
      "Visualize defensive coverage, identify exposure gaps, and understand how security investments support real operational defense.",
  },
];

export function ServiceGrid(): JSX.Element {
  return (
    <section
      aria-labelledby="services-heading"
      className="mx-auto max-w-6xl px-6 py-16"
    >
      <h2
        id="services-heading"
        className="text-2xl font-semibold text-ink-primary"
      >
        Four assessments. One operating system.
      </h2>
      <p className="mt-2 max-w-2xl text-ink-secondary">
        Each service ships in-app with editable workspaces, plain-English client
        views, and PDF + XLSX deliverables that follow your filename
        conventions.
      </p>
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {SERVICES.map((s) => (
          <Card key={s.title}>
            <CardHeader>
              <CardTitle>{s.title}</CardTitle>
              <CardDescription>{s.description}</CardDescription>
            </CardHeader>
            <CardBody>
              <p className="text-xs uppercase tracking-wider text-ink-tertiary">
                Includes:
                <span className="ml-2 normal-case tracking-normal text-ink-secondary">
                  editable consultant workspace, exec rollup, audit-logged AI
                  extractions.
                </span>
              </p>
            </CardBody>
          </Card>
        ))}
      </div>
    </section>
  );
}
