"use client";
import * as React from "react";

import { Card, CardBody, CardHeader, CardTitle } from "@shield/design-system";

import { PillarNavigation } from "./PillarNavigation";
import { QuestionField } from "./QuestionField";
import type {
  Question,
  QuestionnaireDefinition,
  Responses,
  ResponseValue,
} from "./types";

import type { JSX } from "react";

export interface QuestionnaireRendererProps {
  definition: QuestionnaireDefinition;
  responses: Responses;
  /** Called after a single field's value changes. Caller is responsible for
   * any debouncing + persistence. The renderer just bubbles up. */
  onChange: (questionId: string, value: ResponseValue) => void;
  /** Validation errors keyed by question id. */
  errors?: Record<string, string>;
  /** Optional active-section override; otherwise the first section. */
  activeSectionId?: string;
  onActiveSectionChange?: (id: string) => void;
  /** Optional save-status indicator slot rendered in the header. */
  trailing?: React.ReactNode;
}

function isAnswered(value: ResponseValue | undefined): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim() !== "";
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

function sectionProgress(questions: Question[], responses: Responses): number {
  if (questions.length === 0) return 1;
  const answered = questions.filter((q) => isAnswered(responses[q.id])).length;
  return answered / questions.length;
}

export function QuestionnaireRenderer({
  definition,
  responses,
  onChange,
  errors,
  activeSectionId,
  onActiveSectionChange,
  trailing,
}: QuestionnaireRendererProps): JSX.Element {
  const [localActive, setLocalActive] = React.useState(
    activeSectionId ?? definition.sections[0]?.id ?? "",
  );
  const active = activeSectionId ?? localActive;
  const activeSection =
    definition.sections.find((s) => s.id === active) ?? definition.sections[0];

  function setActive(id: string): void {
    setLocalActive(id);
    onActiveSectionChange?.(id);
  }

  const progress = React.useMemo(() => {
    const out: Record<string, number> = {};
    for (const section of definition.sections) {
      out[section.id] = sectionProgress(section.questions, responses);
    }
    return out;
  }, [definition, responses]);

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-ink-primary">
            {definition.title}
          </h2>
          {definition.subtitle ? (
            <p className="text-sm text-ink-secondary">{definition.subtitle}</p>
          ) : null}
        </div>
        {trailing ? <div>{trailing}</div> : null}
      </header>

      <PillarNavigation
        sections={definition.sections}
        activeId={active}
        onChange={setActive}
        progress={progress}
      />

      {activeSection ? (
        <div
          role="region"
          id={`section-${activeSection.id}`}
          aria-label={activeSection.title}
          className="flex flex-col gap-4"
        >
          {activeSection.description ? (
            <p className="text-sm text-ink-secondary">
              {activeSection.description}
            </p>
          ) : null}
          {activeSection.questions.map((question) => (
            <Card key={question.id}>
              <CardHeader>
                <CardTitle className="text-base">
                  {question.prompt}
                  {question.required ? (
                    <span
                      aria-hidden="true"
                      className="ml-1 text-status-danger-fg"
                    >
                      *
                    </span>
                  ) : null}
                </CardTitle>
              </CardHeader>
              <CardBody>
                <QuestionField
                  question={question}
                  value={responses[question.id]}
                  onChange={(v) => onChange(question.id, v)}
                  error={errors?.[question.id]}
                />
              </CardBody>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
