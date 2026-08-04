"use client";
import { Field, inputClasses } from "../Field";
import type { IntakePatchRequest } from "@/lib/intake/types";

import type { JSX } from "react";

export interface Step3ContactProps {
  defaults: {
    display_name: string | null;
    title: string | null;
    phone: string | null;
    timezone: string | null;
    email: string | null;
  };
  onSave: (patch: IntakePatchRequest) => void;
}

export function Step3Contact({
  defaults,
  onSave,
}: Step3ContactProps): JSX.Element {
  function save<K extends keyof IntakePatchRequest>(
    key: K,
    value: IntakePatchRequest[K],
  ): void {
    onSave({ [key]: value } as IntakePatchRequest);
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-secondary">
        Confirm your contact details. We pre-fill what we already have on file.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field id="display_name" label="Full name" required>
          <input
            id="display_name"
            type="text"
            defaultValue={defaults.display_name ?? ""}
            onBlur={(e) => save("display_name", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field
          id="email"
          label="Email"
          hint="Locked — sign in with a different account to change."
        >
          <input
            id="email"
            type="email"
            defaultValue={defaults.email ?? ""}
            readOnly
            className={`${inputClasses} cursor-not-allowed opacity-70`}
          />
        </Field>
        <Field id="title" label="Title">
          <input
            id="title"
            type="text"
            defaultValue={defaults.title ?? ""}
            onBlur={(e) => save("title", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field id="phone" label="Phone">
          <input
            id="phone"
            type="tel"
            defaultValue={defaults.phone ?? ""}
            onBlur={(e) => save("phone", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field
          id="timezone"
          label="Time zone"
          hint="IANA format, e.g. America/New_York. Defaults to UTC."
        >
          <input
            id="timezone"
            type="text"
            defaultValue={defaults.timezone ?? ""}
            onBlur={(e) => save("timezone", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
      </div>
    </div>
  );
}
