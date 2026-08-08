"use client";
import * as React from "react";

import { StatusPill } from "@shield/design-system";

import { fetchAttackAiInputs } from "@/lib/attack/client";
import type { AttackAiInputs } from "@/lib/attack/types";

import type { JSX } from "react";

/**
 * What this mapping will run against — shown BEFORE it runs.
 *
 * The workspace used to report a single number, `23 tools available`, and only
 * after the run had finished. An admin could not see which capabilities were in
 * play or which document they came from. That blindness is how a run with ZERO
 * capabilities wrote 607 fabricated gaps across 633 techniques on 2026-08-07 —
 * a catastrophic-looking posture that was entirely an artifact of no inventory
 * being loaded (N-033).
 *
 * Progressive disclosure on purpose: the summary is three lines so it costs
 * nothing on an already-long page, and the full line-by-line table is one click
 * away for the moment an admin needs to check a specific tool.
 *
 * This never gates Run AI. The typed 409 in the API is the only guard; this is
 * disclosure.
 */

function formatKb(bytes: number): string {
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function AttackAiInputsPanel({
  serviceId,
}: {
  serviceId: string;
}): JSX.Element {
  const [inputs, setInputs] = React.useState<AttackAiInputs | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetchAttackAiInputs(serviceId)
      .then((res) => {
        if (cancelled) return;
        setInputs(res);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Couldn't load what this mapping will use.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [serviceId]);

  if (error) {
    // FAIL LOUDLY. A panel that quietly vanished would read as "no capabilities",
    // which is the exact misreading this component exists to prevent.
    return (
      <p className="text-sm text-status-danger-fg" role="alert">
        {error}
      </p>
    );
  }
  if (!inputs) {
    return (
      <p className="text-sm text-ink-tertiary" aria-live="polite">
        Checking what this mapping will use…
      </p>
    );
  }

  const empty = inputs.tools_sent === 0;

  return (
    <div
      className="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-sunken p-3"
      data-testid="attack-ai-inputs"
    >
      <p
        className={`text-sm font-medium ${empty ? "text-status-warning-fg" : "text-ink-primary"}`}
      >
        {empty
          ? "No security capabilities will be sent — this mapping would report every technique as a gap."
          : `Mapping against ${inputs.tools_sent} security ${
              inputs.tools_sent === 1 ? "capability" : "capabilities"
            } from ${inputs.lists.length} Tech Debt ${
              inputs.lists.length === 1 ? "list" : "lists"
            }.`}
      </p>

      {inputs.awaiting_signoff_count > 0 ||
      inputs.items_without_source_document > 0 ||
      inputs.lists.some((l) => !l.is_latest_for_service) ? (
        <div className="flex flex-wrap gap-2">
          {inputs.awaiting_signoff_count > 0 ? (
            <StatusPill tone="warning">
              {inputs.awaiting_signoff_count} awaiting security sign-off
            </StatusPill>
          ) : null}
          {inputs.items_without_source_document > 0 ? (
            <StatusPill tone="neutral">
              {inputs.items_without_source_document} with no source document
            </StatusPill>
          ) : null}
          {inputs.lists.some((l) => !l.is_latest_for_service) ? (
            <StatusPill tone="info">
              Includes a superseded list version
            </StatusPill>
          ) : null}
        </div>
      ) : null}

      {inputs.documents.length > 0 ? (
        <ul className="flex flex-col gap-1 text-sm">
          {inputs.documents.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2">
              <span className="truncate text-ink-secondary" title={d.title}>
                {d.title}
              </span>
              <span className="text-xs text-ink-tertiary">
                {formatKb(d.size_bytes)} · {d.item_count} capabilit
                {d.item_count === 1 ? "y" : "ies"}
              </span>
              <a
                href={`/api/proxy/artifacts/${d.id}/download`}
                className="rounded-md border border-border px-2 py-1 text-xs font-medium text-ink-primary hover:bg-surface-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
              >
                Download
              </a>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Every non-discarded list version feeds the mapping, superseded ones
          included. Said in words rather than left to be inferred — it surprises
          people, and inferring it from a version number is not disclosure. */}
      {inputs.lists.some((l) => !l.is_latest_for_service) ? (
        <p className="text-xs text-ink-secondary">
          Every non-discarded capability list counts, including superseded
          versions — a tool removed in a later version is still offered to the
          model. Discard a list in its Tech Debt workspace to take it out.
        </p>
      ) : null}

      {inputs.items.length > 0 ? (
        <details data-testid="attack-ai-inputs-table">
          <summary className="cursor-pointer text-sm font-medium text-brand-600 hover:text-brand-500">
            Show all {inputs.items.length} capabilities
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <caption className="sr-only">
                Every security capability being sent to the ATT&amp;CK mapping
              </caption>
              <thead className="text-xs uppercase tracking-wide text-ink-tertiary">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Capability
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Vendor
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Category
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Security functions
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    From list
                  </th>
                </tr>
              </thead>
              <tbody>
                {inputs.items.map((item, i) => (
                  <tr
                    key={`${item.capability_list_id}-${item.name}-${i}`}
                    className="border-t border-border-subtle"
                  >
                    <th
                      scope="row"
                      className="py-1 pr-3 font-medium text-ink-primary"
                    >
                      {item.name}
                      {item.awaiting_signoff ? (
                        <span className="ml-2 text-xs font-normal text-status-warning-fg">
                          awaiting sign-off
                        </span>
                      ) : null}
                    </th>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {item.vendor ?? "—"}
                    </td>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {item.category ?? "—"}
                    </td>
                    <td className="py-1 pr-3 text-ink-secondary">
                      {item.security_functions.length > 0
                        ? item.security_functions.join(", ")
                        : "—"}
                    </td>
                    <td className="py-1 text-ink-secondary">
                      {item.list_label}
                      {item.list_is_superseded ? " (superseded)" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </div>
  );
}
