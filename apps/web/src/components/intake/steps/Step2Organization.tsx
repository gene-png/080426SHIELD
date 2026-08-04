"use client";
import { Field, inputClasses, selectClasses } from "../Field";
import type {
  ClientProfilePatch,
  IntakeStateResponse,
} from "@/lib/intake/types";

import type { JSX } from "react";

export interface Step2OrganizationProps {
  state: IntakeStateResponse;
  onSave: (patch: ClientProfilePatch) => void;
}

const SIZE_BANDS = [
  { value: "", label: "Choose…" },
  { value: "1-50", label: "1–50" },
  { value: "51-200", label: "51–200" },
  { value: "201-500", label: "201–500" },
  { value: "501-1000", label: "501–1,000" },
  { value: "1001-5000", label: "1,001–5,000" },
  { value: "5001+", label: "5,001+" },
];

export function Step2Organization({
  state,
  onSave,
}: Step2OrganizationProps): JSX.Element {
  const c = state.client;

  function saveField<K extends keyof ClientProfilePatch>(
    key: K,
    value: ClientProfilePatch[K],
  ): void {
    onSave({ [key]: value } as ClientProfilePatch);
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-secondary">
        Tell us about your organization. Fields save automatically when you tab
        away.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field id="legal_name" label="Legal name" required>
          <input
            id="legal_name"
            type="text"
            defaultValue={
              c?.legal_name === "(pending intake)" ? "" : (c?.legal_name ?? "")
            }
            onBlur={(e) => saveField("legal_name", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field id="dba_name" label="DBA / Trade name">
          <input
            id="dba_name"
            type="text"
            defaultValue={c?.dba_name ?? ""}
            onBlur={(e) => saveField("dba_name", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field id="website" label="Website" hint="e.g. https://example.gov">
          <input
            id="website"
            type="url"
            defaultValue={c?.website ?? ""}
            onBlur={(e) => saveField("website", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field id="size_band" label="Headcount band">
          <select
            id="size_band"
            defaultValue={c?.size_band ?? ""}
            onBlur={(e) => saveField("size_band", e.target.value || undefined)}
            className={selectClasses}
          >
            {SIZE_BANDS.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
        </Field>
        <Field
          id="industry"
          label="Industry"
          hint="e.g. Defense, Civilian, State & Local, Healthcare"
        >
          <input
            id="industry"
            type="text"
            defaultValue={c?.industry ?? ""}
            onBlur={(e) => saveField("industry", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
      </div>

      <h3 className="mt-2 text-sm font-semibold uppercase tracking-wider text-ink-tertiary">
        Address
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field
          id="address_line1"
          label="Address line 1"
          className="sm:col-span-2"
        >
          <input
            id="address_line1"
            type="text"
            defaultValue={c?.address_line1 ?? ""}
            onBlur={(e) =>
              saveField("address_line1", e.target.value || undefined)
            }
            className={inputClasses}
          />
        </Field>
        <Field
          id="address_line2"
          label="Address line 2"
          className="sm:col-span-2"
        >
          <input
            id="address_line2"
            type="text"
            defaultValue={c?.address_line2 ?? ""}
            onBlur={(e) =>
              saveField("address_line2", e.target.value || undefined)
            }
            className={inputClasses}
          />
        </Field>
        <Field id="city" label="City">
          <input
            id="city"
            type="text"
            defaultValue={c?.city ?? ""}
            onBlur={(e) => saveField("city", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field id="state" label="State / Region">
          <input
            id="state"
            type="text"
            defaultValue={c?.state ?? ""}
            onBlur={(e) => saveField("state", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
        <Field id="postal_code" label="Postal code">
          <input
            id="postal_code"
            type="text"
            defaultValue={c?.postal_code ?? ""}
            onBlur={(e) =>
              saveField("postal_code", e.target.value || undefined)
            }
            className={inputClasses}
          />
        </Field>
        <Field id="country" label="Country">
          <input
            id="country"
            type="text"
            defaultValue={c?.country ?? "United States"}
            onBlur={(e) => saveField("country", e.target.value || undefined)}
            className={inputClasses}
          />
        </Field>
      </div>
    </div>
  );
}
