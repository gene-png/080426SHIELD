import Link from "next/link";

import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  StatusPill,
  type StatusTone,
} from "@shield/design-system";

import type { ClientDeliverable } from "@/components/documents/DocumentsList";
import {
  ValueLoopCard,
  type ValueSummary,
} from "@/components/home/ValueLoopCard";
import {
  ASSESSMENT_SERVICE_TYPES,
  SERVICE_LABELS,
  type AssessmentResponse,
  type ServiceType,
} from "@/lib/intake/types";

import type { JSX } from "react";

/**
 * The signed-in client landing dashboard (Master Spec §6.4). Purely
 * presentational and server-rendered — every input is fetched upstream in the
 * /home server component. §6.4 is explicit about what this surface must NOT
 * show: scoring math, audit internals, or raw AI output. So this component
 * renders phase labels and next steps only — never a number, tier, or score.
 *
 * Four bands (§6.4):
 *   1. Greeting.
 *   2. Hero — "Your {service} report is ready" + View/Download, shown ONLY
 *      when a released deliverable exists (else next-step guidance, so there is
 *      never a dead end, §12).
 *   3. Per-service status grid (intake → in progress → under review → report
 *      ready), derived from existing engagement/assessment status — no new
 *      scoring.
 *   4. "What's waiting on you" (open self-assessments + unread messages) and
 *      recent activity.
 */

export interface HomeDashboardProps {
  greetingName: string;
  deliverables: ClientDeliverable[];
  engagements: AssessmentResponse[];
  unreadMessages: number;
  valueSummary: ValueSummary | null;
}

const DATE_FMT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
});

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : DATE_FMT.format(d);
}

function serviceLabel(kind: string, fallback: string): string {
  return SERVICE_LABELS[kind as ServiceType] ?? fallback;
}

/**
 * A client-safe phase for one engagement, spanning intake → report ready. A
 * released deliverable for the service always wins (the report is out). No
 * scoring is read — only the lifecycle status the client already sees on
 * /assessments.
 */
function phaseFor(
  e: AssessmentResponse,
  hasReleasedDeliverable: boolean,
): { label: string; tone: StatusTone } {
  if (hasReleasedDeliverable) return { label: "Report ready", tone: "success" };
  switch (e.assessment_status) {
    case "approved":
      return { label: "Finalizing your report", tone: "info" };
    case "submitted":
      return { label: "Under review", tone: "warning" };
    case "draft":
      return { label: "In progress", tone: "info" };
    default:
      return e.status === "released"
        ? { label: "Report ready", tone: "success" }
        : { label: "Getting started", tone: "neutral" };
  }
}

export function HomeDashboard({
  greetingName,
  deliverables,
  engagements,
  unreadMessages,
  valueSummary,
}: HomeDashboardProps): JSX.Element {
  // Which services already have a released report (drives the grid + hero).
  const releasedServiceIds = new Set(deliverables.map((d) => d.service_id));
  // Ordered released_at desc upstream, so [0] is the freshest report.
  const latest = deliverables[0] ?? null;
  const openSelfAssessments = engagements.filter(
    (e) =>
      ASSESSMENT_SERVICE_TYPES.includes(e.service_type) &&
      e.assessment_status === "draft",
  );

  return (
    <div className="flex flex-col gap-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold text-ink-primary">
          Welcome back, {greetingName}
        </h1>
        <p className="max-w-prose text-sm text-ink-secondary">
          Your engagement at a glance — what&apos;s ready, what&apos;s in
          motion, and what needs you next.
        </p>
      </header>

      {/* Band 2: hero (report ready) or next-step guidance. */}
      {latest ? (
        <section
          aria-labelledby="hero-heading"
          className="rounded-xl border border-status-success-border bg-status-success-bg px-6 py-6"
        >
          <StatusPill tone="success" withDot>
            Report ready
          </StatusPill>
          <h2
            id="hero-heading"
            className="mt-3 text-2xl font-semibold text-ink-primary"
          >
            Your {serviceLabel(latest.service_kind, latest.service_title)}{" "}
            report is ready
          </h2>
          <p className="mt-1 text-sm text-ink-secondary">
            Released {formatDate(latest.released_at)}. View it alongside every
            report your analyst has shared with you.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              href="/documents"
              className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
            >
              View reports
            </Link>
            {latest.pdf_artifact_id ? (
              <a
                href={`/api/proxy/artifacts/${latest.pdf_artifact_id}/download`}
                className="rounded-md border border-border bg-surface-card px-4 py-2 text-sm font-semibold text-ink-primary hover:bg-surface-sunken"
                {...(latest.pdf_filename
                  ? { download: latest.pdf_filename }
                  : {})}
              >
                Download PDF
              </a>
            ) : null}
          </div>
        </section>
      ) : (
        <section
          aria-labelledby="hero-heading"
          className="rounded-xl border border-border bg-surface-card px-6 py-6"
        >
          <h2
            id="hero-heading"
            className="text-2xl font-semibold text-ink-primary"
          >
            {openSelfAssessments.length > 0
              ? "Pick up where you left off"
              : "Let's get your first assessment started"}
          </h2>
          <p className="mt-1 max-w-prose text-sm text-ink-secondary">
            {openSelfAssessments.length > 0
              ? "You have a self-assessment in progress. Finish it and your analyst takes it from there."
              : "Start an assessment to begin. Your reports will appear here the moment your analyst releases them."}
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            {openSelfAssessments.length > 0 ? (
              <Link
                href={`/self-assessment/${openSelfAssessments[0].service_id}?type=${openSelfAssessments[0].service_type}`}
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
              >
                Continue self-assessment
              </Link>
            ) : (
              <Link
                href="/assessments"
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600"
              >
                Start an assessment
              </Link>
            )}
          </div>
        </section>
      )}

      {/* Band 2.5: cross-service value loop (§2.5), only once data is released. */}
      {valueSummary ? <ValueLoopCard summary={valueSummary} /> : null}

      {/* Band 3: per-service status grid. */}
      <section aria-labelledby="services-heading" className="space-y-3">
        <h2
          id="services-heading"
          className="text-lg font-semibold text-ink-primary"
        >
          Your services
        </h2>
        {engagements.length === 0 ? (
          <EmptyState
            title="No services yet"
            description="When you start an assessment, its progress will show up here."
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {engagements.map((e) => {
              const phase = phaseFor(e, releasedServiceIds.has(e.service_id));
              return (
                <li key={e.service_id}>
                  <Card>
                    <CardBody className="flex flex-col gap-2">
                      <p className="text-sm font-semibold text-ink-primary">
                        {e.title}
                      </p>
                      <p className="text-xs text-ink-secondary">
                        {SERVICE_LABELS[e.service_type]}
                      </p>
                      <StatusPill tone={phase.tone} withDot>
                        {phase.label}
                      </StatusPill>
                    </CardBody>
                  </Card>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Band 4: waiting-on-you + recent activity. */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Waiting on you</CardTitle>
          </CardHeader>
          <CardBody>
            {openSelfAssessments.length === 0 && unreadMessages === 0 ? (
              <p className="text-sm text-ink-secondary">
                Nothing needs your attention right now. We&apos;ll flag anything
                that does.
              </p>
            ) : (
              <ul className="flex flex-col gap-3 text-sm">
                {openSelfAssessments.map((e) => (
                  <li
                    key={e.service_id}
                    className="flex flex-wrap items-center justify-between gap-2"
                  >
                    <span className="text-ink-secondary">
                      Finish your {SERVICE_LABELS[e.service_type]}
                    </span>
                    <Link
                      href={`/self-assessment/${e.service_id}?type=${e.service_type}`}
                      className="font-semibold text-brand-600 hover:text-brand-500"
                    >
                      Continue →
                    </Link>
                  </li>
                ))}
                {unreadMessages > 0 ? (
                  <li className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-ink-secondary">
                      {unreadMessages} unread{" "}
                      {unreadMessages === 1 ? "message" : "messages"} from your
                      analyst
                    </span>
                    <Link
                      href="/messages"
                      className="font-semibold text-brand-600 hover:text-brand-500"
                    >
                      Open messages →
                    </Link>
                  </li>
                ) : null}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardBody>
            {deliverables.length === 0 ? (
              <p className="text-sm text-ink-secondary">
                Released reports will show up here as your engagement
                progresses.
              </p>
            ) : (
              <ul className="flex flex-col gap-3 text-sm">
                {deliverables.slice(0, 4).map((d) => (
                  <li
                    key={d.id}
                    className="flex flex-wrap items-center justify-between gap-2"
                  >
                    <span className="text-ink-secondary">
                      {serviceLabel(d.service_kind, d.service_title)} report
                      released
                    </span>
                    <span className="whitespace-nowrap text-ink-tertiary">
                      {formatDate(d.released_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
