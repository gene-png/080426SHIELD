"use client";
import { Field, textareaClasses } from "../Field";
import type { IntakeStateResponse } from "@/lib/intake/types";

import type { JSX } from "react";

export interface Step4SystemsProps {
  state: IntakeStateResponse;
  onSave: (prompting_context: string) => void;
}

export function Step4Systems({
  state,
  onSave,
}: Step4SystemsProps): JSX.Element {
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-secondary">
        Give us a one-paragraph picture of the systems in scope. Categorization,
        ATO status, hosting, and POAM volume can wait — we&apos;ll capture those
        in the assessment workspace. For now, a free-text orientation is enough
        to plan the assessment.
      </p>
      <Field
        id="prompting_context"
        label="Systems and context"
        hint="What systems are in scope? What categorization? What hosting? Anything that gives a consultant a fast on-ramp."
      >
        <textarea
          id="prompting_context"
          defaultValue={state.client?.prompting_context ?? ""}
          onBlur={(e) => onSave(e.target.value)}
          className={textareaClasses}
          rows={8}
        />
      </Field>
    </div>
  );
}
