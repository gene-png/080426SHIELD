"use client";
import * as React from "react";

import { cn } from "@shield/design-system";

import {
  Field,
  inputClasses,
  selectClasses,
  textareaClasses,
} from "../intake/Field";

import type { Question, ResponseValue } from "./types";

import type { JSX } from "react";

export interface QuestionFieldProps {
  question: Question;
  value: ResponseValue | undefined;
  onChange: (next: ResponseValue) => void;
  error?: string;
}

const SCORE_LABELS_DEFAULT: [string, string, string] = [
  "Not in place",
  "Partial",
  "In place",
];

const TRISTATE_LABELS_DEFAULT: [string, string, string] = ["Yes", "No", "N/A"];

export function QuestionField({
  question,
  value,
  onChange,
  error,
}: QuestionFieldProps): JSX.Element {
  switch (question.type) {
    case "short_text":
      return (
        <Field
          id={question.id}
          label={question.prompt}
          hint={question.hint}
          error={error}
        >
          <input
            id={question.id}
            type="text"
            maxLength={question.maxLength}
            placeholder={question.placeholder}
            defaultValue={(value as string | undefined) ?? ""}
            onBlur={(e) => onChange(e.target.value || null)}
            className={inputClasses}
          />
        </Field>
      );

    case "long_text":
      return (
        <Field
          id={question.id}
          label={question.prompt}
          hint={question.hint}
          error={error}
        >
          <textarea
            id={question.id}
            maxLength={question.maxLength}
            placeholder={question.placeholder}
            rows={question.rows ?? 4}
            defaultValue={(value as string | undefined) ?? ""}
            onBlur={(e) => onChange(e.target.value || null)}
            className={textareaClasses}
          />
        </Field>
      );

    case "number":
      return (
        <Field
          id={question.id}
          label={
            question.unit
              ? `${question.prompt} (${question.unit})`
              : question.prompt
          }
          hint={question.hint}
          error={error}
        >
          <input
            id={question.id}
            type="number"
            min={question.min}
            max={question.max}
            step={question.step}
            defaultValue={(value as number | undefined) ?? ""}
            onBlur={(e) =>
              onChange(e.target.value === "" ? null : Number(e.target.value))
            }
            className={inputClasses}
          />
        </Field>
      );

    case "score_0_2": {
      const labels = question.labels ?? SCORE_LABELS_DEFAULT;
      return (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-ink-primary">
            {question.prompt}
            {question.required ? (
              <span aria-hidden="true" className="ml-1 text-status-danger-fg">
                *
              </span>
            ) : null}
          </legend>
          {question.hint ? (
            <p className="text-xs text-ink-tertiary">{question.hint}</p>
          ) : null}
          <div role="radiogroup" className="flex flex-wrap gap-2">
            {[0, 1, 2].map((score) => {
              const isOn = value === score;
              return (
                <label
                  key={score}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm",
                    isOn
                      ? "border-border-focus bg-brand-50 text-ink-primary"
                      : "border-border bg-surface-card text-ink-secondary hover:text-ink-primary",
                  )}
                >
                  <input
                    type="radio"
                    name={question.id}
                    value={score}
                    checked={isOn}
                    onChange={() => onChange(score)}
                    className="h-4 w-4 text-brand-500"
                  />
                  <span>
                    <span className="font-semibold">{score}</span>{" "}
                    <span className="text-ink-tertiary">— {labels[score]}</span>
                  </span>
                </label>
              );
            })}
          </div>
          {error ? (
            <p className="text-xs text-status-danger-fg" role="alert">
              {error}
            </p>
          ) : null}
        </fieldset>
      );
    }

    case "choice":
      return (
        <Field
          id={question.id}
          label={question.prompt}
          hint={question.hint}
          error={error}
        >
          <select
            id={question.id}
            defaultValue={(value as string | undefined) ?? ""}
            onBlur={(e) => onChange(e.target.value || null)}
            className={selectClasses}
          >
            <option value="">Choose…</option>
            {question.choices.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
      );

    case "multi": {
      const current = Array.isArray(value) ? (value as string[]) : [];
      return (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-ink-primary">
            {question.prompt}
            {question.required ? (
              <span aria-hidden="true" className="ml-1 text-status-danger-fg">
                *
              </span>
            ) : null}
          </legend>
          {question.hint ? (
            <p className="text-xs text-ink-tertiary">{question.hint}</p>
          ) : null}
          <div className="flex flex-col gap-1">
            {question.choices.map((c) => {
              const checked = current.includes(c.value);
              return (
                <label
                  key={c.value}
                  className="flex cursor-pointer items-start gap-2 text-sm text-ink-primary"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const next = checked
                        ? current.filter((x) => x !== c.value)
                        : [...current, c.value];
                      onChange(next);
                    }}
                    className="mt-1 h-4 w-4 rounded-sm border-border text-brand-500"
                  />
                  <span>
                    <span className="font-medium">{c.label}</span>
                    {c.description ? (
                      <span className="block text-xs text-ink-tertiary">
                        {c.description}
                      </span>
                    ) : null}
                  </span>
                </label>
              );
            })}
          </div>
          {error ? (
            <p className="text-xs text-status-danger-fg" role="alert">
              {error}
            </p>
          ) : null}
        </fieldset>
      );
    }

    case "yes_no":
      return (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-ink-primary">
            {question.prompt}
          </legend>
          {question.hint ? (
            <p className="text-xs text-ink-tertiary">{question.hint}</p>
          ) : null}
          <div role="radiogroup" className="flex gap-2">
            {[
              { v: true, label: "Yes" },
              { v: false, label: "No" },
            ].map((opt) => {
              const isOn = value === opt.v;
              return (
                <label
                  key={opt.label}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm",
                    isOn
                      ? "border-border-focus bg-brand-50"
                      : "border-border bg-surface-card hover:text-ink-primary",
                  )}
                >
                  <input
                    type="radio"
                    name={question.id}
                    checked={isOn}
                    onChange={() => onChange(opt.v)}
                    className="h-4 w-4 text-brand-500"
                  />
                  <span>{opt.label}</span>
                </label>
              );
            })}
          </div>
          {error ? (
            <p className="text-xs text-status-danger-fg" role="alert">
              {error}
            </p>
          ) : null}
        </fieldset>
      );

    case "tristate": {
      const labels = question.labels ?? TRISTATE_LABELS_DEFAULT;
      const options: { key: "yes" | "no" | "n_a"; label: string }[] = [
        { key: "yes", label: labels[0] },
        { key: "no", label: labels[1] },
        { key: "n_a", label: labels[2] },
      ];
      return (
        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium text-ink-primary">
            {question.prompt}
          </legend>
          {question.hint ? (
            <p className="text-xs text-ink-tertiary">{question.hint}</p>
          ) : null}
          <div role="radiogroup" className="flex gap-2">
            {options.map((opt) => {
              const isOn = value === opt.key;
              return (
                <label
                  key={opt.key}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm",
                    isOn
                      ? "border-border-focus bg-brand-50"
                      : "border-border bg-surface-card",
                  )}
                >
                  <input
                    type="radio"
                    name={question.id}
                    checked={isOn}
                    onChange={() => onChange(opt.key)}
                    className="h-4 w-4 text-brand-500"
                  />
                  <span>{opt.label}</span>
                </label>
              );
            })}
          </div>
          {error ? (
            <p className="text-xs text-status-danger-fg" role="alert">
              {error}
            </p>
          ) : null}
        </fieldset>
      );
    }
  }
}
