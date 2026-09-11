"use client";
import * as React from "react";

import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  cn,
} from "@shield/design-system";

import { SelfAssessmentSubmitted } from "@/components/self-assessment/SelfAssessmentSubmitted";
import { ZtStagePicker } from "@/components/admin/zt/ZtStagePicker";
import { ZtMaturityReference } from "@/components/zt/ZtMaturityReference";
import {
  fetchCatalog,
  fetchSelfAssessment,
  patchSelfAssessmentAnswer,
  submitSelfAssessment,
} from "@/lib/zt/client";
import { describeSaveError } from "@/lib/describe-save-error";
import type {
  CatalogPillar,
  ZtAnswer,
  ZtSelfAssessmentAnswerPatch,
  ZtAssessment,
  ZtCatalog,
  ZtFramework,
} from "@/lib/zt/types";

import type { JSX } from "react";

export function ZtSelfAssessment({
  serviceId,
  framework,
}: {
  serviceId: string;
  framework: ZtFramework;
}): JSX.Element {
  const [catalog, setCatalog] = React.useState<ZtCatalog | null>(null);
  const [assessment, setAssessment] = React.useState<ZtAssessment | null>(null);
  const [target, setTarget] = React.useState<number>(3);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  // #283. The optimistic write below used to be reverted by nothing and
  // reported by nothing: the row showed the new value, the PATCH 422'd, and a
  // reload silently lost it. Core principle 2 — never a lie that something
  // succeeded — and the API half of that was fixed in #195/#282 while this
  // layer kept telling the client it had worked.
  const [saveError, setSaveError] = React.useState<string | null>(null);
  // Guards the failure re-fetch below: a later save's truth must not be
  // overwritten by an earlier one's recovery. Same mechanism, and the same
  // reason, as `assessmentSeq` in the admin workspaces.
  const saveSeq = React.useRef(0);
  const [submitted, setSubmitted] = React.useState(false);
  const [pillarIdx, setPillarIdx] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    Promise.all([fetchCatalog(framework), fetchSelfAssessment(serviceId)])
      .then(([cat, a]) => {
        if (cancelled) return;
        setCatalog(cat);
        setAssessment(a);
        if (a?.client_target_stage) setTarget(a.client_target_stage);
        if (a && a.status !== "draft") setSubmitted(true);
      })
      .catch((err) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [serviceId, framework]);

  const answersByCode = React.useMemo(() => {
    const map: Record<string, ZtAnswer> = {};
    for (const a of assessment?.answers ?? []) map[a.capability_code] = a;
    return map;
  }, [assessment]);

  // Per-pillar answered/total, in catalog order. Drives the progress bar,
  // the per-pillar badges, and the submit gate.
  const pillarStats = React.useMemo(() => {
    const pillars = catalog?.pillars ?? [];
    return pillars.map((p) => {
      const total = p.capabilities.length;
      const answered = p.capabilities.filter(
        (c) => answersByCode[c.code]?.maturity_stage != null,
      ).length;
      return { code: p.code, name: p.name, answered, total };
    });
  }, [catalog, answersByCode]);

  // UX finding 13: pillar-level progress alone did not tell the client how much
  // of the assessment remained. Capability-level counts drive "24 of 37".
  const answeredTotal = pillarStats.reduce((n, s) => n + s.answered, 0);
  const capabilityTotal = pillarStats.reduce((n, s) => n + s.total, 0);
  const answeredPct = capabilityTotal
    ? Math.round((answeredTotal / capabilityTotal) * 100)
    : 0;
  const firstUnansweredIdx = pillarStats.findIndex((s) => s.answered < s.total);

  const everyPillarStarted =
    pillarStats.length > 0 && pillarStats.every((s) => s.answered > 0);
  const pillarsComplete = pillarStats.filter(
    (s) => s.total > 0 && s.answered === s.total,
  ).length;

  async function onAnswerUpdate(
    answerId: string,
    patch: ZtSelfAssessmentAnswerPatch,
  ): Promise<void> {
    // Name the row. The alert renders once, at the bottom of a page that
    // can carry 106 subcategories, so "that change" leaves the client
    // unable to tell which answer was lost.
    const subject =
      assessment?.answers.find((a) => a.id === answerId)?.capability_code ??
      "That change";
    setAssessment((curr) =>
      curr
        ? {
            ...curr,
            answers: curr.answers.map((a) =>
              a.id === answerId ? ({ ...a, ...patch } as ZtAnswer) : a,
            ),
          }
        : curr,
    );
    try {
      const updated = await patchSelfAssessmentAnswer(answerId, patch);
      // Cleared HERE, on a confirmed success, and not at the top of this
      // function. A first draft cleared it before the request, so a client
      // whose answer to one row was refused lost the message the instant
      // they touched another -- while that answer was still gone.
      setSaveError(null);
      setAssessment((curr) =>
        curr
          ? {
              ...curr,
              answers: curr.answers.map((a) =>
                a.id === answerId ? updated : a,
              ),
            }
          : curr,
      );
    } catch (err) {
      // RE-FETCH, do not restore a snapshot. A first draft captured the
      // row before the optimistic write and put it back on failure. That
      // reads as safe and is not: both fields auto-save, so a second edit
      // to the same row captures the OPTIMISTIC value, and its revert then
      // discards a change the server had already confirmed.
      //
      // The three admin workspaces already solve this with a sequence-
      // guarded re-fetch, which is a DERIVATION of server truth rather
      // than a synchronisation with a stale copy. Using theirs rather
      // than inventing a weaker one three files away.
      setSaveError(describeSaveError(err, subject));
      const seq = ++saveSeq.current;
      try {
        const truth = await fetchSelfAssessment(serviceId);
        if (seq === saveSeq.current) setAssessment(truth);
      } catch {
        // The re-fetch failed too. The message above still stands and is
        // the honest one: we cannot show what the server has. Silence
        // here would put us back where #283 started.
      }
    }
  }

  async function onSubmit(): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const next = await submitSelfAssessment(serviceId, {
        target_stage: target,
      });
      setAssessment(next);
      setSubmitted(true);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Submit failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Couldn&apos;t load your self-assessment</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-status-danger-fg">{loadError}</p>
        </CardBody>
      </Card>
    );
  }
  if (!catalog || !assessment) {
    return (
      <p className="text-sm text-ink-tertiary">Loading your self-assessment…</p>
    );
  }
  if (submitted) {
    return <SelfAssessmentSubmitted />;
  }

  const targetStages = catalog.stages.filter((s) => s.stage >= 2);
  const pillars = catalog.pillars;
  const idx = Math.min(pillarIdx, pillars.length - 1);
  const pillar: CatalogPillar | undefined = pillars[idx];
  const stat = pillarStats[idx];
  const isLast = idx >= pillars.length - 1;
  const incomplete = pillarStats.filter((s) => s.answered === 0);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>1. Your maturity target</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col gap-3">
          <p className="text-sm text-ink-secondary">
            Pick the maturity stage you want to reach. We measure the gap
            between your answers below and this goal to recommend what to
            prioritize.
          </p>
          <ZtMaturityReference framework={framework} />
          <div className="flex flex-wrap gap-2">
            {targetStages.map((s) => (
              <button
                key={s.stage}
                type="button"
                onClick={() => setTarget(s.stage)}
                aria-pressed={target === s.stage}
                className={cn(
                  "max-w-xs rounded-md border px-4 py-2 text-left text-sm transition-colors",
                  target === s.stage
                    ? "border-brand-500 bg-brand-50 text-ink-primary"
                    : "border-border bg-surface-card text-ink-secondary hover:border-border-strong",
                )}
              >
                <span className="block font-semibold">
                  Stage {s.stage} · {s.label}
                </span>
                <span className="block text-xs text-ink-tertiary">
                  {s.description}
                </span>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>2. Self-assessment</CardTitle>
            <span className="text-sm font-medium text-ink-tertiary">
              Pillar {idx + 1} of {pillars.length}
            </span>
          </div>
        </CardHeader>
        <CardBody className="flex flex-col gap-4">
          <p className="text-sm text-ink-secondary">
            This assessment covers{" "}
            <span className="font-medium text-ink-primary">
              {pillars.length} pillars
            </span>
            . Step through each one and rate every capability for where your
            organization stands today — you must address all pillars before you
            can submit. Use Previous / Next to move between them.
          </p>

          {/* Overall pillar progress */}
          <div>
            <div
              className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-sunken"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={pillars.length}
              aria-valuenow={pillarsComplete}
              aria-label={`${pillarsComplete} of ${pillars.length} pillars fully answered`}
            >
              <div
                className="h-full rounded-pill bg-brand-500 transition-all"
                style={{
                  width: `${pillars.length ? (pillarsComplete / pillars.length) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <p className="text-xs text-ink-tertiary">
                <span className="font-semibold text-ink-secondary">
                  {answeredTotal} of {capabilityTotal} answered
                </span>{" "}
                ({answeredPct}%) · {pillarsComplete} of {pillars.length} pillars
                fully answered
              </p>
              {firstUnansweredIdx >= 0 ? (
                <button
                  type="button"
                  onClick={() => setPillarIdx(firstUnansweredIdx)}
                  className="text-xs font-medium text-brand-600 underline hover:text-brand-700"
                >
                  Review unanswered items
                </button>
              ) : null}
            </div>
          </div>

          {/* Pillar stepper: shows every pillar + its completion at a glance */}
          <ol className="flex flex-wrap gap-1.5" aria-label="Pillars">
            {pillarStats.map((s, i) => {
              const done = s.total > 0 && s.answered === s.total;
              const started = s.answered > 0;
              const isCurrent = i === idx;
              return (
                <li key={s.code}>
                  <button
                    type="button"
                    onClick={() => setPillarIdx(i)}
                    aria-current={isCurrent ? "step" : undefined}
                    // UX finding 14: the tabs showed bare abbreviations (ID, DV,
                    // NW …). The full name is now visible, and the accessible
                    // name also carries progress so screen-reader users get the
                    // same at-a-glance completion the badge gives sighted users.
                    aria-label={`${s.code} ${s.name} — ${s.answered} of ${s.total} answered`}
                    title={`${s.code} · ${s.name}`}
                    className={cn(
                      "flex items-center gap-1 rounded-pill border px-2.5 py-1 text-xs font-medium transition-colors",
                      isCurrent
                        ? "border-brand-500 bg-brand-50 text-ink-primary"
                        : "border-border bg-surface-card text-ink-secondary hover:border-border-strong",
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold",
                        done
                          ? "bg-status-success-bg text-status-success-fg"
                          : started
                            ? "bg-status-info-bg text-status-info-fg"
                            : "bg-surface-sunken text-ink-tertiary",
                      )}
                    >
                      {done ? "✓" : i + 1}
                    </span>
                    <span aria-hidden>
                      <span className="font-semibold">{s.code}</span>
                      <span className="ml-1 hidden sm:inline">{s.name}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          {/* Current pillar */}
          {pillar && stat ? (
            <section
              aria-label={`${pillar.code} ${pillar.name}`}
              className="flex flex-col gap-4 rounded-md border border-border-subtle bg-surface-card p-4"
            >
              <header className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-base font-semibold text-ink-primary">
                    {pillar.code} · {pillar.name}
                  </h3>
                  <p className="mt-0.5 text-sm text-ink-secondary">
                    {pillar.purpose}
                  </p>
                </div>
                <span
                  className={cn(
                    "shrink-0 rounded-pill px-2 py-0.5 text-xs font-semibold",
                    stat.answered === stat.total
                      ? "bg-status-success-bg text-status-success-fg"
                      : stat.answered > 0
                        ? "bg-status-info-bg text-status-info-fg"
                        : "bg-surface-sunken text-ink-tertiary",
                  )}
                >
                  {stat.answered} of {stat.total} answered
                </span>
              </header>

              <ul className="flex flex-col gap-3">
                {pillar.capabilities.map((cap) => {
                  const ans = answersByCode[cap.code];
                  if (!ans) return null;
                  return (
                    <li
                      key={cap.code}
                      className="rounded-md border border-border-subtle bg-surface-sunken p-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-mono text-ink-tertiary">
                            {cap.code}
                          </p>
                          <p className="text-sm font-medium text-ink-primary">
                            {cap.name}
                          </p>
                          <p className="mt-1 text-sm text-ink-secondary">
                            {cap.outcome}
                          </p>
                        </div>
                        <ZtStagePicker
                          value={ans.maturity_stage}
                          stages={catalog.stages}
                          ariaLabel={`Maturity stage for ${cap.code}`}
                          onChange={(next) => {
                            void onAnswerUpdate(ans.id, {
                              maturity_stage: next,
                            });
                          }}
                        />
                      </div>
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
                          aria-label={`Notes for ${cap.code}`}
                          // KEYED ON THE CONFIRMED VALUE. `defaultValue` makes
                          // this an uncontrolled input, and React does not
                          // reset a user-dirtied textarea when that prop
                          // changes -- so reverting state left the REFUSED text
                          // on screen under an alert saying it had been
                          // restored. #283's own symptom, surviving its fix, on
                          // the one field most likely to trip `max_length`.
                          // Changing the key remounts the box, which is what
                          // actually puts the server's value back in front of
                          // the client.
                          key={`${ans.id}:${ans.notes ?? ""}`}
                          defaultValue={ans.notes ?? ""}
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

              {/* Within-pillar navigation */}
              <div className="flex items-center justify-between gap-2 border-t border-border-subtle pt-3">
                <button
                  type="button"
                  onClick={() => setPillarIdx((i) => Math.max(0, i - 1))}
                  disabled={idx === 0}
                  className={cn(
                    "rounded-md border px-3 py-1.5 text-sm font-medium transition",
                    idx === 0
                      ? "cursor-not-allowed border-border-subtle text-ink-tertiary opacity-50"
                      : "border-border text-ink-secondary hover:bg-surface-sunken hover:text-ink-primary",
                  )}
                >
                  ← Previous
                </button>
                {isLast ? (
                  <span className="text-xs text-ink-tertiary">
                    Last pillar — review the others, then submit below.
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      setPillarIdx((i) => Math.min(pillars.length - 1, i + 1))
                    }
                    className="rounded-md border border-brand-500 bg-brand-500 px-4 py-1.5 text-sm font-semibold text-ink-on-accent transition hover:bg-brand-600"
                  >
                    Next: {pillars[idx + 1]?.code} →
                  </button>
                )}
              </div>
            </section>
          ) : null}
        </CardBody>
      </Card>

      {saveError ? (
        <div
          role="alert"
          className="rounded-md border border-status-danger-border bg-status-danger-bg px-4 py-3 text-sm text-status-danger-fg"
        >
          {saveError}
        </div>
      ) : null}
      {submitError ? (
        <div
          role="alert"
          className="rounded-md border border-status-danger-border bg-status-danger-bg px-4 py-3 text-sm text-status-danger-fg"
        >
          {submitError}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-tertiary">
          {everyPillarStarted ? (
            "All pillars have answers — you can submit for review."
          ) : (
            <>
              Add at least one answer to every pillar before submitting. Still
              needs attention:{" "}
              <span className="font-medium text-ink-secondary">
                {incomplete.map((s) => s.code).join(", ")}
              </span>
              .
            </>
          )}
        </p>
        <button
          type="button"
          onClick={() => void onSubmit()}
          disabled={submitting || !everyPillarStarted}
          title={
            everyPillarStarted
              ? undefined
              : "Answer at least one capability in every pillar first."
          }
          className="rounded-md bg-brand-500 px-5 py-2.5 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Submitting…" : "Submit for review"}
        </button>
      </div>
    </div>
  );
}
