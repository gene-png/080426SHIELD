"use client";
import * as React from "react";

import type {
  CatalogFunction,
  CsfAnswer,
  CsfAnswerPatch,
  CsfCatalog,
  CsfInterviewQuestion,
} from "@/lib/csf/types";

import { TierPicker } from "./TierPicker";

import type { JSX } from "react";

export interface CsfQuestionnaireProps {
  catalog: CsfCatalog;
  answersByCode: Record<string, CsfAnswer>;
  /** Interview prompts keyed by the subcategory code each one informs.
   * Supplemental context for the assessor; sparse by design. */
  questionsByCode?: Record<string, CsfInterviewQuestion[]>;
  readOnly?: boolean;
  onAnswerUpdate: (
    answerId: string,
    patch: CsfAnswerPatch,
  ) => void | Promise<void>;
}

interface TabState {
  active: string;
}

function FunctionTabBar({
  functions,
  active,
  onChange,
}: {
  functions: CatalogFunction[];
  active: string;
  onChange: (code: string) => void;
}): JSX.Element {
  return (
    <div
      role="tablist"
      aria-label="CSF functions"
      className="flex flex-wrap gap-1 border-b border-border-subtle"
    >
      {functions.map((fn) => {
        const selected = fn.code === active;
        return (
          <button
            key={fn.code}
            role="tab"
            type="button"
            aria-selected={selected}
            id={`csf-tab-${fn.code}`}
            aria-controls={`csf-panel-${fn.code}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(fn.code)}
            className={[
              "rounded-t-md px-3 py-2 text-sm font-semibold border-b-2 -mb-px transition",
              selected
                ? "border-brand-500 text-ink-primary"
                : "border-transparent text-ink-tertiary hover:text-ink-secondary",
            ].join(" ")}
          >
            {fn.code} · {fn.name}
          </button>
        );
      })}
    </div>
  );
}

export function CsfQuestionnaire({
  catalog,
  answersByCode,
  questionsByCode = {},
  readOnly = false,
  onAnswerUpdate,
}: CsfQuestionnaireProps): JSX.Element {
  const [tab, setTab] = React.useState<TabState>({
    active: catalog.functions[0]?.code ?? "GV",
  });

  const activeFn = catalog.functions.find((f) => f.code === tab.active);

  return (
    <section
      aria-labelledby="csf-questionnaire-heading"
      className="flex flex-col gap-4"
    >
      <h2
        id="csf-questionnaire-heading"
        className="text-lg font-semibold text-ink-primary"
      >
        CSF 2.0 questionnaire
      </h2>
      <FunctionTabBar
        functions={catalog.functions}
        active={tab.active}
        onChange={(code) => setTab({ active: code })}
      />
      {activeFn ? (
        <div
          role="tabpanel"
          id={`csf-panel-${activeFn.code}`}
          aria-labelledby={`csf-tab-${activeFn.code}`}
          className="flex flex-col gap-6"
        >
          <p className="text-sm text-ink-secondary">{activeFn.purpose}</p>
          {activeFn.categories.map((cat) => (
            <section key={cat.code} className="flex flex-col gap-3">
              <header>
                <h3 className="text-sm font-semibold uppercase tracking-[0.15em] text-ink-tertiary">
                  {cat.code} · {cat.name}
                </h3>
                <p className="text-sm text-ink-secondary">{cat.purpose}</p>
              </header>
              <ul className="flex flex-col gap-3">
                {cat.subcategories.map((sub) => {
                  const ans = answersByCode[sub.code];
                  if (!ans) return null;
                  return (
                    <li
                      key={sub.code}
                      className="rounded-md border border-border-subtle bg-surface-card p-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-mono text-ink-tertiary">
                            {sub.code}
                          </p>
                          <p className="text-sm font-medium text-ink-primary">
                            {sub.name}
                          </p>
                          <p className="mt-1 text-sm text-ink-secondary">
                            {sub.outcome}
                          </p>
                        </div>
                        <TierPicker
                          value={ans.maturity_tier}
                          disabled={readOnly}
                          onChange={(next) => {
                            void onAnswerUpdate(ans.id, {
                              maturity_tier: next,
                            });
                          }}
                          ariaLabel={`Maturity tier for ${sub.code}`}
                        />
                      </div>
                      {questionsByCode[sub.code]?.length ? (
                        <div className="mt-3 flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-sunken p-2.5">
                          {questionsByCode[sub.code].map((q) => (
                            <div key={q.external_id}>
                              <p className="text-xs font-semibold uppercase tracking-wide text-ink-tertiary">
                                Interview · {q.section_name}
                              </p>
                              <p className="mt-0.5 text-sm text-ink-primary">
                                {q.stem}
                              </p>
                              {q.cues.length ? (
                                <ul className="mt-1 list-disc pl-4 text-xs text-ink-secondary">
                                  {q.cues.map((cue, i) => (
                                    <li key={i}>{cue}</li>
                                  ))}
                                </ul>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      <details className="mt-2">
                        <summary className="cursor-pointer text-xs font-medium text-ink-tertiary hover:text-ink-secondary">
                          Notes {ans.notes ? "·" : ""}{" "}
                          {ans.notes ? (
                            <span className="font-normal text-ink-secondary">
                              {ans.notes.length > 60
                                ? `${ans.notes.slice(0, 60)}…`
                                : ans.notes}
                            </span>
                          ) : null}
                        </summary>
                        <textarea
                          aria-label={`Notes for ${sub.code}`}
                          defaultValue={ans.notes ?? ""}
                          disabled={readOnly}
                          rows={3}
                          onBlur={(e) => {
                            const v = e.currentTarget.value.trim();
                            if (v === (ans.notes ?? "")) return;
                            void onAnswerUpdate(ans.id, { notes: v });
                          }}
                          className="mt-2 w-full rounded-md border border-border bg-surface-card p-2 text-sm text-ink-primary focus:border-brand-500 focus:outline-hidden"
                          placeholder="Evidence, references, exceptions…"
                        />
                      </details>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      ) : null}
    </section>
  );
}
