"use client";
import * as React from "react";

import {
  BLOCK_HEADING,
  CHOOSE_ZT_FRAMEWORK,
  NEEDS_CSF_OR_ZT,
  ZT_FRAMEWORK_OPTIONS,
  ZT_RADIO_LEGEND,
  noAssessmentLine,
  requiredLabel,
  type SelectionChoice,
  type SelectionModel,
} from "@/lib/risk/selection";

import type { JSX } from "react";

/**
 * RR-1 (for #1122), design note §2: the block above Generate. ATT&CK is
 * always included; CSF and Zero Trust are ticked by default when eligible; a
 * service that is the only one of CSF and ZT eligible is required. With two
 * Zero Trust frameworks the radio starts unanswered (fail closed, Q2), and
 * Generate stays disabled until it is answered (copy 17). Labels are the
 * server's, from the gate's rows.
 */
export function RiskSelectionBlock({
  model,
  choice,
  onChange,
  blocked,
  disabled,
}: {
  model: SelectionModel;
  choice: SelectionChoice;
  onChange: (next: SelectionChoice) => void;
  /** Why Generate cannot run with this choice, or null. */
  blocked: "needs_csf_or_zt" | "zt_framework" | null;
  /** Work in flight, or the page is leaving: nothing may change. */
  disabled: boolean;
}): JSX.Element {
  const twoFrameworks = model.zt.length > 1;
  const ztOn = model.ztRequired || choice.zt;
  const ztLabel = twoFrameworks ? "Zero Trust" : (model.zt[0]?.label ?? "");
  return (
    <fieldset
      className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm"
      data-testid="risk-selection-block"
    >
      <legend className="px-1 font-semibold text-ink-primary">
        {BLOCK_HEADING}
      </legend>
      {model.attack.map((svc) => (
        <label key={svc.service_id} className="flex items-center gap-2">
          <input type="checkbox" checked disabled readOnly />
          {requiredLabel(svc.label)}
        </label>
      ))}
      {model.csf !== null ? (
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={model.csfRequired || choice.csf}
            disabled={disabled || model.csfRequired}
            onChange={(ev) => onChange({ ...choice, csf: ev.target.checked })}
          />
          {model.csfRequired ? requiredLabel(model.csf.label) : model.csf.label}
        </label>
      ) : null}
      {model.zt.length > 0 ? (
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={ztOn}
              disabled={disabled || model.ztRequired}
              onChange={(ev) => onChange({ ...choice, zt: ev.target.checked })}
            />
            {model.ztRequired ? requiredLabel(ztLabel) : ztLabel}
          </label>
          {twoFrameworks ? (
            <fieldset className="ml-6 flex flex-col gap-1">
              <legend className="text-ink-secondary">{ZT_RADIO_LEGEND}</legend>
              {ZT_FRAMEWORK_OPTIONS.map((opt) => (
                <label key={opt.value} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="risk-zero-trust-framework"
                    value={opt.value}
                    checked={choice.ztFramework === opt.value}
                    disabled={disabled || !ztOn}
                    onChange={() =>
                      onChange({ ...choice, ztFramework: opt.value })
                    }
                  />
                  {opt.label}
                </label>
              ))}
              {ztOn && blocked === "zt_framework" ? (
                <p
                  className="text-status-warning-fg"
                  data-testid="risk-selection-zt-hint"
                >
                  {CHOOSE_ZT_FRAMEWORK}
                </p>
              ) : null}
            </fieldset>
          ) : null}
        </div>
      ) : null}
      {model.ineligible.map((svc) => (
        <p
          key={svc.service_id}
          className="text-ink-tertiary"
          data-testid="risk-selection-ineligible"
        >
          {noAssessmentLine(svc.label)}
        </p>
      ))}
      {blocked === "needs_csf_or_zt" ? (
        <p
          className="text-status-warning-fg"
          data-testid="risk-selection-needs-csf-or-zt"
        >
          {NEEDS_CSF_OR_ZT}
        </p>
      ) : null}
    </fieldset>
  );
}
