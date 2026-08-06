"use client";
import * as React from "react";

import { Field, inputClasses } from "../Field";
import type { IntakePatchRequest } from "@/lib/intake/types";

import type { JSX } from "react";

/**
 * Step 3 — who Kentro should talk to about this engagement.
 *
 * Two things this step gets right that it previously did not (UX finding 9):
 *
 * 1. **Values round-trip.** `title`, `phone` and `timezone` used to be passed in
 *    as hardcoded nulls, so anything typed here came back blank on the next
 *    visit even though the API had saved and was returning it. The step now
 *    reads the contact the API resolved.
 * 2. **The person filling this in may not be the contact.** Email is locked to
 *    the signed-in account, which is correct for identity and wrong for a POC —
 *    an assistant or procurement lead completing the form on someone else's
 *    behalf had no way to say so, so the engagement recorded the wrong person
 *    and a consultant would contact them. The override says it explicitly.
 */

export interface Step3ContactProps {
  defaults: {
    display_name: string | null;
    title: string | null;
    phone: string | null;
    timezone: string | null;
    email: string | null;
  };
  /** The client's primary-contact override, when one has been saved. */
  override: {
    primary_contact_name: string | null;
    primary_contact_email: string | null;
    primary_contact_title: string | null;
    primary_contact_phone: string | null;
  };
  onSave: (patch: IntakePatchRequest) => void;
}

export function Step3Contact({
  defaults,
  override,
  onSave,
}: Step3ContactProps): JSX.Element {
  // An override exists once it names someone: a title or phone on their own
  // redirect nothing, and the server applies the same rule.
  const hasOverride = Boolean(
    override.primary_contact_name || override.primary_contact_email,
  );
  const [notTheContact, setNotTheContact] = React.useState(hasOverride);

  function save<K extends keyof IntakePatchRequest>(
    key: K,
    value: IntakePatchRequest[K],
  ): void {
    onSave({ [key]: value } as IntakePatchRequest);
  }

  function saveOverride(
    key:
      | "primary_contact_name"
      | "primary_contact_email"
      | "primary_contact_title"
      | "primary_contact_phone",
    value: string | undefined,
  ): void {
    onSave({ client: { [key]: value ?? null } } as IntakePatchRequest);
  }

  function toggle(checked: boolean): void {
    setNotTheContact(checked);
    if (!checked) {
      // Clearing the flag must clear the stored override too. Leaving the
      // values behind would keep redirecting mail to someone the user just
      // said is not the contact — the exact failure this affordance prevents.
      onSave({
        client: {
          primary_contact_name: null,
          primary_contact_email: null,
          primary_contact_title: null,
          primary_contact_phone: null,
        },
      } as IntakePatchRequest);
    }
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

      <div className="rounded-md border border-slate-200 p-4">
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={notTheContact}
            onChange={(e) => toggle(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            <span className="font-medium text-ink-primary">
              I am not the primary contact for this engagement
            </span>
            <span className="block text-ink-secondary">
              Tell us who to contact instead. Your account details above stay as
              they are.
            </span>
          </span>
        </label>

        {notTheContact ? (
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field id="primary_contact_name" label="Contact name" required>
              <input
                id="primary_contact_name"
                type="text"
                defaultValue={override.primary_contact_name ?? ""}
                onBlur={(e) =>
                  saveOverride(
                    "primary_contact_name",
                    e.target.value || undefined,
                  )
                }
                className={inputClasses}
              />
            </Field>
            <Field
              id="primary_contact_email"
              label="Contact email"
              hint="Leave blank to keep using your own address for updates."
            >
              <input
                id="primary_contact_email"
                type="email"
                defaultValue={override.primary_contact_email ?? ""}
                onBlur={(e) =>
                  saveOverride(
                    "primary_contact_email",
                    e.target.value || undefined,
                  )
                }
                className={inputClasses}
              />
            </Field>
            <Field id="primary_contact_title" label="Contact title">
              <input
                id="primary_contact_title"
                type="text"
                defaultValue={override.primary_contact_title ?? ""}
                onBlur={(e) =>
                  saveOverride(
                    "primary_contact_title",
                    e.target.value || undefined,
                  )
                }
                className={inputClasses}
              />
            </Field>
            <Field id="primary_contact_phone" label="Contact phone">
              <input
                id="primary_contact_phone"
                type="tel"
                defaultValue={override.primary_contact_phone ?? ""}
                onBlur={(e) =>
                  saveOverride(
                    "primary_contact_phone",
                    e.target.value || undefined,
                  )
                }
                className={inputClasses}
              />
            </Field>
          </div>
        ) : null}
      </div>
    </div>
  );
}
