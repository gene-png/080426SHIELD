"use client";
import Link from "next/link";
import * as React from "react";

import { QuestionnaireRenderer } from "@/components/questionnaire";
import type {
  QuestionnaireDefinition,
  Responses,
  ResponseValue,
} from "@/components/questionnaire/types";

import type { JSX } from "react";

/**
 * Dev-only preview that exercises the QuestionnaireRenderer end-to-end with
 * a hand-rolled definition spanning every question type. Real CSF / ATT&CK
 * definitions ship in Phase 4 + 5. The route is unlisted (no nav link to
 * it) and the layout flags it as preview-only.
 */

const PREVIEW: QuestionnaireDefinition = {
  id: "preview",
  title: "Renderer preview",
  subtitle: "Every question type, end-to-end. Dev-only.",
  sections: [
    {
      id: "text",
      title: "Text",
      description: "Short and long text fields.",
      questions: [
        {
          id: "preview.short",
          type: "short_text",
          prompt: "What is the system's CSAM ID?",
          placeholder: "e.g. SYS-12345",
          hint: "Optional. Matches the row in your CSAM export.",
        },
        {
          id: "preview.long",
          type: "long_text",
          prompt: "Briefly describe the system's mission.",
          rows: 4,
          maxLength: 1000,
        },
      ],
    },
    {
      id: "scores",
      title: "Scores",
      description: "0–2 scores and yes/no/n-a.",
      questions: [
        {
          id: "preview.score.gov",
          type: "score_0_2",
          prompt: "Governance dimension score",
          hint: "0 = not in place; 1 = partial; 2 = fully in place.",
          required: true,
        },
        {
          id: "preview.score.policy",
          type: "score_0_2",
          prompt: "Policy & Process dimension score",
        },
        {
          id: "preview.tristate",
          type: "tristate",
          prompt: "Is this control under continuous monitoring?",
        },
        {
          id: "preview.yes_no",
          type: "yes_no",
          prompt: "Has this been tested in the last 12 months?",
        },
      ],
    },
    {
      id: "structured",
      title: "Structured",
      description: "Choice + multi + number.",
      questions: [
        {
          id: "preview.choice",
          type: "choice",
          prompt: "FIPS-199 categorization",
          choices: [
            { value: "high", label: "HIGH" },
            { value: "moderate", label: "MODERATE" },
            { value: "low", label: "LOW" },
          ],
        },
        {
          id: "preview.multi",
          type: "multi",
          prompt: "Which platforms are in scope?",
          choices: [
            { value: "windows", label: "Windows" },
            { value: "linux", label: "Linux" },
            { value: "macos", label: "macOS" },
            { value: "kubernetes", label: "Kubernetes" },
            { value: "saas", label: "SaaS" },
          ],
        },
        {
          id: "preview.number",
          type: "number",
          prompt: "Open POAMs",
          unit: "count",
          min: 0,
          step: 1,
        },
      ],
    },
  ],
};

export default function QuestionnairePreviewPage(): JSX.Element {
  const [responses, setResponses] = React.useState<Responses>({});

  function onChange(id: string, value: ResponseValue): void {
    setResponses((prev) => ({ ...prev, [id]: value }));
  }

  return (
    <main className="mx-auto w-full max-w-4xl px-6 py-10">
      <div className="mb-4 flex items-center justify-between">
        <p className="inline-flex rounded-pill bg-status-warning-bg px-2.5 py-0.5 text-xs font-semibold text-status-warning-fg">
          Dev preview
        </p>
        <Link href="/" className="text-sm text-brand-500 hover:text-brand-600">
          ← Back to landing
        </Link>
      </div>
      <QuestionnaireRenderer
        definition={PREVIEW}
        responses={responses}
        onChange={onChange}
      />
      <details className="mt-8 rounded-md border border-border-subtle bg-surface-card p-4">
        <summary className="cursor-pointer text-sm font-semibold text-ink-primary">
          Live responses
        </summary>
        <pre className="mt-2 overflow-x-auto text-xs text-ink-secondary">
          {JSON.stringify(responses, null, 2)}
        </pre>
      </details>
    </main>
  );
}
