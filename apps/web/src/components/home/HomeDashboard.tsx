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

import type { ClientDeliverable } from "@/components/results/ResultsList";
import {
  ValueLoopCard,
  type ValueSummary,
} from "@/components/home/ValueLoopCard";
import { dashboardPathFor } from "@/lib/dashboards/routes";
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

/**
 * True when the client still owes their own self-assessment on this service —
 * the one thing on /home whose next move belongs to the client rather than the
 * analyst.
 *
 * ONE predicate, two readers: the "Action required" bucket and the hero's
 * "Continue self-assessment" call to action. They used to be written out
 * separately, which is how the same self-assessment ended up rendered in two
 * places at once; sharing the predicate means they cannot disagree.
 */
function needsClient(e: AssessmentResponse): boolean {
  return (
    ASSESSMENT_SERVICE_TYPES.includes(e.service_type) &&
    e.assessment_status === "draft"
  );
}

/** Task-status buckets, in render order (C3). */
type BucketKey = "action" | "progress" | "results";

const BUCKETS: ReadonlyArray<{
  key: BucketKey;
  title: string;
  blurb: string;
}> = [
  {
    key: "action",
    title: "Action required",
    blurb: "These are waiting on you before they can move forward.",
  },
  {
    key: "progress",
    title: "In progress",
    blurb: "With your analyst. Nothing needed from you right now.",
  },
  {
    key: "results",
    title: "Results available",
    blurb: "Released and ready to read.",
  },
];

/**
 * Which bucket owns a service — that is, who has the next move.
 *
 * EXACTLY ONE bucket per service, which is the whole point: a client reads one
 * heading instead of comparing four phase pills, and nothing is listed twice.
 * Released wins over everything (the report is out, there is nothing left to
 * wait on), then the client's own outstanding work, then everything else, which
 * by definition sits with the analyst.
 *
 * This is ownership, not progress. The card's phase pill still says which phase
 * the engagement is in, and the two answer different questions — §6.4 keeps the
 * six-stage consultant bar off this surface entirely.
 */
function bucketFor(
  e: AssessmentResponse,
  hasReleasedDeliverable: boolean,
): BucketKey {
  if (hasReleasedDeliverable || e.status === "released") return "results";
  if (needsClient(e)) return "action";
  return "progress";
}

/**
 * What the client would actually DO with this service, in their words.
 *
 * Finding #17 asks for one named primary action per service. The bucket heading
 * says who owns the next move; this says what that move is. Keyed off the
 * bucket rather than re-deriving from status, so the label can never disagree
 * with the group the card is filed under.
 *
 * Rendered as text inside the card's existing link — never its own <a>. A
 * nested anchor is invalid HTML and would give every card two tab stops
 * pointing at the same destination.
 */
const BUCKET_ACTIONS: Record<BucketKey, string> = {
  action: "Resume assessment",
  progress: "View status",
  results: "View results",
};

/**
 * Where a service card goes when clicked. Mirrors the card's own phase so the
 * destination always matches the status the client just read (Navigation_Spec
 * §12: no card is a dead end, and no link lands somewhere unrelated):
 *
 *   report ready  → that service's dashboard, or /results if it has none
 *   in progress   → the self-assessment questionnaire to resume
 *   anything else → /assessments, the list this service came from
 */
function serviceHref(
  e: AssessmentResponse,
  hasReleasedDeliverable: boolean,
): string {
  if (hasReleasedDeliverable) {
    return dashboardPathFor(e.service_type, e.service_id) ?? "/results";
  }
  if (
    ASSESSMENT_SERVICE_TYPES.includes(e.service_type) &&
    e.assessment_status === "draft"
  ) {
    return `/self-assessment/${e.service_id}?type=${e.service_type}`;
  }
  return "/assessments";
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
  const openSelfAssessments = engagements.filter(needsClient);
  // Every engagement filed under exactly one bucket, in arrival order within it.
  const grouped: Record<BucketKey, AssessmentResponse[]> = {
    action: [],
    progress: [],
    results: [],
  };
  for (const e of engagements) {
    grouped[bucketFor(e, releasedServiceIds.has(e.service_id))].push(e);
  }

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
              href="/results"
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

      {/* Band 3: services grouped by who owns the next move (C3). */}
      <section aria-labelledby="services-heading" className="space-y-6">
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
        ) : null}
        {BUCKETS.map(({ key, title, blurb }) => {
          const items = grouped[key];
          // Unread messages need the client too, but have no service card of
          // their own — they belong under the same heading rather than in a
          // second "what needs me" list somewhere else on the page.
          const showMessages = key === "action" && unreadMessages > 0;
          if (items.length === 0 && !showMessages) return null;
          const count = items.length + (showMessages ? 1 : 0);
          return (
            <section
              key={key}
              aria-labelledby={`bucket-${key}`}
              className="space-y-3"
            >
              <div className="space-y-0.5">
                <h3
                  id={`bucket-${key}`}
                  className="text-sm font-semibold uppercase tracking-wide text-ink-primary"
                >
                  {title}{" "}
                  <span className="font-normal text-ink-tertiary">
                    ({count})
                  </span>
                </h3>
                <p className="text-xs text-ink-secondary">{blurb}</p>
              </div>
              {showMessages ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-surface-card px-4 py-3 text-sm">
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
                </div>
              ) : null}
              {items.length > 0 ? (
                <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {items.map((e) => {
                    const released = releasedServiceIds.has(e.service_id);
                    const phase = phaseFor(e, released);
                    return (
                      <li key={e.service_id}>
                        <Link
                          href={serviceHref(e, released)}
                          className="block h-full rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
                        >
                          <Card className="h-full transition-colors hover:border-brand-500">
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
                              {/* Finding #17's primary action. A span, not a
                                  link — the whole card is already the link.
                                  mt-auto pins it to the bottom so the actions
                                  line up across cards of differing heights. */}
                              <span className="mt-auto pt-1 text-sm font-semibold text-brand-600">
                                {BUCKET_ACTIONS[key]} →
                              </span>
                            </CardBody>
                          </Card>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </section>
          );
        })}
      </section>

      {/* Band 4: recent activity.
          "Waiting on you" used to sit beside this and listed the same open
          self-assessments the grid above already showed — the duplication C3
          names. "Action required" is now the single answer to "what needs me",
          so this band is history only. */}
      <div className="grid gap-6">
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
