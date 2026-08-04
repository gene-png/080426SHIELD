"use client";
import Link from "next/link";
import * as React from "react";

import {
  Card,
  CardBody,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  StatusPill,
} from "@shield/design-system";

import { fetchIntakeQueue, fulfillServiceRequest } from "@/lib/admin/client";
import {
  workspaceHref,
  type AdminIntakeQueueResponse,
} from "@/lib/admin/types";
import {
  CSF_PROFILES,
  CSF_TARGET_TIERS,
  SERVICE_LABELS,
  ZT_TARGET_STAGES,
} from "@/lib/intake/types";

import type { JSX } from "react";

type ServiceRequestRow = AdminIntakeQueueResponse["service_requests"][number];

/** The maturity target the client set at intake, formatted for display. */
function clientTarget(
  s: AdminIntakeQueueResponse["service_requests"][number],
): string | null {
  if (s.service_type === "nist_csf") {
    const tier = CSF_TARGET_TIERS.find(
      (t) => t.value === s.csf_target_tier,
    )?.label;
    const profile = CSF_PROFILES.find((p) => p.value === s.csf_profile)?.label;
    return [tier, profile].filter(Boolean).join(" · ") || null;
  }
  if (
    s.service_type === "zero_trust_cisa" ||
    s.service_type === "zero_trust_dod"
  ) {
    return (
      ZT_TARGET_STAGES[s.service_type].find(
        (x) => x.value === s.zt_target_stage,
      )?.label ?? null
    );
  }
  return null;
}

function row(label: string, value: string | null | undefined): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-1 border-b border-border-subtle py-2 last:border-b-0 sm:grid-cols-3">
      <dt className="text-sm font-medium text-ink-secondary">{label}</dt>
      <dd className="text-sm text-ink-primary sm:col-span-2">
        {value ? (
          value
        ) : (
          <span className="italic text-ink-tertiary">Not provided</span>
        )}
      </dd>
    </div>
  );
}

function serviceTone(
  s: AdminIntakeQueueResponse["service_requests"][number],
): "info" | "success" | "warning" | "neutral" {
  if (s.fulfilled_service_id) return "success";
  if (s.declined_at) return "warning";
  if (s.service_type === "consultation") return "neutral";
  return "info";
}

function serviceState(s: ServiceRequestRow): string {
  if (s.fulfilled_service_id) return "Published";
  if (s.declined_at) return "Declined";
  return "Awaiting review";
}

function ReadinessItem({
  ok,
  label,
  missingHint,
}: {
  ok: boolean;
  label: string;
  missingHint: string;
}): JSX.Element {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span
        aria-hidden
        className={ok ? "text-status-success-fg" : "text-status-warning-fg"}
      >
        {ok ? "✓" : "⚠"}
      </span>
      <span className="text-ink-secondary">
        <span className="font-medium text-ink-primary">{label}</span>
        {ok ? "" : ` — ${missingHint}`}
      </span>
    </li>
  );
}

/**
 * One service request, with the admin's review checklist + publish action.
 * "Publish for processing" opens the assessment workspace; the readiness
 * items flag intake gaps that would skew the AI assessment.
 */
function ServiceRequestCard({
  s,
  hasContext,
  hasDocuments,
  onPublished,
}: {
  s: ServiceRequestRow;
  hasContext: boolean;
  hasDocuments: boolean;
  onPublished: () => void;
}): JSX.Element {
  const [publishing, setPublishing] = React.useState(false);
  const [publishError, setPublishError] = React.useState<string | null>(null);

  const isConsultation = s.service_type === "consultation";
  const fulfilled = Boolean(s.fulfilled_service_id);
  const target = clientTarget(s);
  const needsTarget =
    s.service_type === "nist_csf" ||
    s.service_type === "zero_trust_cisa" ||
    s.service_type === "zero_trust_dod";
  const href = workspaceHref(s.service_type, s.fulfilled_service_id);

  async function onPublish(): Promise<void> {
    setPublishing(true);
    setPublishError(null);
    try {
      await fulfillServiceRequest(s.id);
      onPublished();
    } catch (err) {
      setPublishError(
        err instanceof Error ? err.message : "Failed to publish.",
      );
    } finally {
      setPublishing(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{SERVICE_LABELS[s.service_type]}</CardTitle>
          <StatusPill tone={serviceTone(s)} withDot>
            {serviceState(s)}
          </StatusPill>
        </div>
        <CardDescription>
          Requested {new Date(s.requested_at).toLocaleString()} by{" "}
          <span className="font-medium text-ink-primary">
            {s.requested_by.display_name ?? s.requested_by.email}
          </span>
          {s.requested_by.title ? ` · ${s.requested_by.title}` : ""}
        </CardDescription>
      </CardHeader>
      <CardBody>
        <dl>
          {row("Email", s.requested_by.email)}
          {target ? row("Client target", target) : null}
          {row(
            "Target deadline",
            s.deadline ? new Date(s.deadline).toLocaleDateString() : null,
          )}
          {row("Notes", s.notes)}
        </dl>

        {isConsultation ? (
          <p className="mt-4 text-sm text-ink-secondary">
            Consultation request — follow up with the client directly. There is
            nothing to publish for processing.
          </p>
        ) : fulfilled ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="text-sm text-status-success-fg">
              ✓ Published for processing.
            </span>
            {href ? (
              <Link
                href={href}
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
              >
                Open workspace →
              </Link>
            ) : null}
          </div>
        ) : (
          <div className="mt-4 rounded-md border border-border-subtle bg-surface-sunken p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-500">
              Review before publishing
            </p>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-secondary">
              <li>
                Confirm the inputs above are complete and specific — vague scope
                makes the AI score from guesses.
              </li>
              <li>Open each uploaded document and remove any raw PII.</li>
              <li>
                Publish to open the assessment workspace and make this intake
                available for AI processing.
              </li>
            </ol>
            <ul className="mt-3 space-y-1">
              {needsTarget ? (
                <ReadinessItem
                  ok={Boolean(target)}
                  label="Assessment target set"
                  missingHint="ask the client to pick a target in step 5"
                />
              ) : null}
              <ReadinessItem
                ok={hasContext}
                label="Systems & scope context"
                missingHint="thin context lowers AI accuracy"
              />
              <ReadinessItem
                ok={hasDocuments}
                label="Supporting documents uploaded"
                missingHint="no evidence to ground the assessment"
              />
            </ul>
            {publishError ? (
              <p role="alert" className="mt-3 text-sm text-status-danger-fg">
                {publishError}
              </p>
            ) : null}
            <button
              type="button"
              onClick={() => void onPublish()}
              disabled={publishing}
              className="mt-3 rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {publishing ? "Publishing…" : "Publish for processing"}
            </button>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function IntakeQueue(): JSX.Element {
  const [state, setState] = React.useState<AdminIntakeQueueResponse | null>(
    null,
  );
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    fetchIntakeQueue()
      .then(setState)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load."),
      );
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Couldn&apos;t load the queue</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-status-danger-fg">{error}</p>
        </CardBody>
      </Card>
    );
  }

  if (!state) {
    return <p className="text-sm text-ink-tertiary">Loading…</p>;
  }

  const c = state.client;
  const submittedAt = state.intake_completed_at
    ? new Date(state.intake_completed_at).toLocaleString()
    : null;
  const hasIntake = c !== null && c.legal_name !== "(pending intake)";
  const hasContext = Boolean(
    c?.prompting_context && c.prompting_context.trim(),
  );
  const hasDocuments = state.artifacts.length > 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">
            Admin
          </p>
          <h1 className="text-3xl font-semibold text-ink-primary">
            Intake queue
          </h1>
          <p className="max-w-prose text-sm text-ink-secondary">
            The queue reflects exactly what the client entered during intake.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {submittedAt ? (
            <StatusPill tone="success" withDot>
              Submitted {submittedAt}
            </StatusPill>
          ) : hasIntake ? (
            <StatusPill tone="warning" withDot>
              In progress — not yet submitted
            </StatusPill>
          ) : (
            <StatusPill tone="neutral" withDot>
              No intake started
            </StatusPill>
          )}
          <StatusPill tone="info">
            {state.total_users} user{state.total_users === 1 ? "" : "s"}
          </StatusPill>
        </div>
      </header>

      {hasIntake ? (
        <Card>
          <CardHeader>
            <CardTitle>Organization</CardTitle>
            <CardDescription>
              From the client&apos;s intake submission.
            </CardDescription>
          </CardHeader>
          <CardBody>
            <dl>
              {row("Legal name", c.legal_name)}
              {row("DBA / Trade name", c.dba_name)}
              {row("Website", c.website)}
              {row("Headcount band", c.size_band)}
              {row("Industry", c.industry)}
              {row(
                "Address",
                [
                  c.address_line1,
                  c.address_line2,
                  c.city,
                  c.state,
                  c.postal_code,
                  c.country,
                ]
                  .filter(Boolean)
                  .join(", ") || null,
              )}
              {row("Systems and context", c.prompting_context)}
            </dl>
          </CardBody>
        </Card>
      ) : (
        <EmptyState
          title="No client intake yet"
          description="When the deployment's primary POC submits intake, it will appear here."
        />
      )}

      <section
        aria-labelledby="service-requests"
        className="flex flex-col gap-3"
      >
        <h2
          id="service-requests"
          className="text-lg font-semibold text-ink-primary"
        >
          Service requests ({state.service_requests.length})
        </h2>
        {state.service_requests.length === 0 ? (
          <EmptyState
            title="No service requests yet"
            description="Each service the client picks at intake becomes a request here."
          />
        ) : (
          <ul className="flex flex-col gap-3">
            {state.service_requests.map((s) => (
              <li key={s.id}>
                <ServiceRequestCard
                  s={s}
                  hasContext={hasContext}
                  hasDocuments={hasDocuments}
                  onPublished={load}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="artifacts" className="flex flex-col gap-3">
        <h2 id="artifacts" className="text-lg font-semibold text-ink-primary">
          Uploaded documents ({state.artifacts.length})
        </h2>
        {state.artifacts.length === 0 ? (
          <EmptyState
            title="No documents uploaded yet"
            description="Files the client attaches during intake will appear here."
          />
        ) : (
          <ul className="flex flex-col gap-1">
            {state.artifacts.map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-surface-card px-3 py-2 text-sm"
              >
                <span
                  className="truncate font-medium text-ink-primary"
                  title={a.title}
                >
                  {a.title}
                </span>
                <span className="shrink-0 text-xs text-ink-tertiary">
                  {(a.size_bytes / 1024).toFixed(1)} KB ·{" "}
                  {new Date(a.uploaded_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
