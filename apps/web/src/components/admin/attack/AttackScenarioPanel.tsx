"use client";

import * as React from "react";

import { RunAiGuard } from "@/components/admin/RunAiGuard";
import { clientFacingError } from "@/lib/describe-save-error";
import { outsideAssessedText } from "@/lib/attack/outsideAssessed";
import {
  createScenario,
  discardScenario,
  fetchScenario,
  fetchScenarios,
  runScenario,
} from "@/lib/attack/scenarios";

import type { AiServes } from "@/lib/aiRuns/types";
import type {
  Scenario,
  ScenarioList as ScenarioListData,
  ScenarioRollup,
  ScenarioSummary,
} from "@/lib/attack/scenarios";
import type { JSX } from "react";

/**
 * The ATT&CK what-if (#802 slice A). Admin only.
 *
 * Remove tools from the last confirmed assessment and compare coverage. Every
 * figure comes from the api, which computes it with R3's rules; nothing here
 * writes to the assessment or the client's view.
 *
 * Copy 1-17 approved on #802; 18 is the advisor's addition (05:05Z). Strings
 * marked NEW are listed for the advisor in the draft PR.
 */

const POLL_MS = 3000;

/**
 * A COPY of `NEEDS_CONFIRMED_MESSAGE` in `app/routes/attack_scenarios.py`,
 * shown when the list says there is no base (no request was refused, so no
 * server sentence arrived). The pointer lives there too.
 */
const NO_BASE =
  "There is no confirmed assessment to compare with yet. Approve the ATT&CK assessment and review every technique in its review queue, then try again.";

/**
 * A COPY of `UNAVAILABLE_MESSAGE` in `app/routes/attack_scenarios.py`, shown
 * before any click while the api says the analysis cannot run (#806).
 */
const UNAVAILABLE = "AI analysis for what-ifs is not available yet.";

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

function affectedLine(n: number): string {
  return n === 1
    ? "1 technique uses these tools and will be re-assessed."
    : `${n} techniques use these tools and will be re-assessed.`;
}

/** Copy 18. */
function scoredHigherLine(n: number): string {
  return n === 1
    ? "1 technique would score higher than today, because the AI credited a remaining tool the last confirmed assessment did not. Check it before relying on the result."
    : `${n} techniques would score higher than today, because the AI credited a remaining tool the last confirmed assessment did not. Check these before relying on the result.`;
}

/** NEW: the techniques a failed batch left with the removal alone. */
function notReassessedLine(n: number): string {
  return n === 1
    ? "1 technique could not be re-assessed because the AI did not answer for it. It shows the removal alone: the removed tools are taken out and nothing else changes."
    : `${n} techniques could not be re-assessed because the AI did not answer for them. They show the removal alone: the removed tools are taken out and nothing else changes.`;
}

/** Copy 12, and NEW sentences for the drop reasons copy 12 does not describe. */
function dropLines(dropped: Record<string, number>): string[] {
  const outside =
    (dropped.technique_outside_slice ?? 0) + (dropped.tool_outside_change ?? 0);
  const unconfirmed = dropped.tool_unconfirmed ?? 0;
  const notLost = dropped.function_not_lost ?? 0;
  const malformed = (dropped.not_boolean ?? 0) + (dropped.not_an_object ?? 0);
  const lines: string[] = [];
  if (outside > 0)
    lines.push(
      `${outside} AI ${plural(outside, "suggestion was", "suggestions were")} set aside because ${plural(outside, "it", "they")} named a tool or a technique outside these changes.`,
    );
  if (unconfirmed > 0)
    lines.push(
      `${unconfirmed} AI ${plural(unconfirmed, "suggestion was", "suggestions were")} set aside because the tool ${plural(unconfirmed, "it", "they")} named could not be matched exactly to one of the client's tools.`,
    );
  if (notLost > 0)
    lines.push(
      `${notLost} AI ${plural(notLost, "suggestion was", "suggestions were")} set aside because ${plural(notLost, "it", "they")} credited Detect, Prevent or Respond where these changes took nothing away.`,
    );
  if (malformed > 0)
    lines.push(
      `${malformed} AI ${plural(malformed, "suggestion was", "suggestions were")} set aside because ${plural(malformed, "it was", "they were")} not in the expected form.`,
    );
  return lines;
}

function approvedText(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString() : "date not recorded";
}

function Rollup({
  heading,
  r,
  testId,
}: {
  heading: string;
  r: ScenarioRollup;
  testId: string;
}): JSX.Element {
  return (
    <div data-testid={testId} className="rounded-md border border-line p-3">
      <h4 className="text-sm font-semibold text-ink-primary">{heading}</h4>
      <p className="text-2xl font-semibold text-ink-primary">
        {r.coverage_pct.toFixed(1)}%
      </p>
      <p className="text-sm text-ink-secondary">
        {r.covered} covered, {r.partial} partial, {r.gap} gap
        {r.pending_review > 0 ? `, ${r.pending_review} pending review` : ""}
      </p>
      {outsideAssessedText(r) === null ? null : (
        <p className="text-sm text-ink-secondary">{outsideAssessedText(r)}</p>
      )}
    </div>
  );
}

type Phase =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; list: ScenarioListData };

export function AttackScenarioPanel({
  serviceId,
  pollMs = POLL_MS,
}: {
  serviceId: string;
  /** How often a running analysis is re-read. Tests shorten it. */
  pollMs?: number;
}): JSX.Element {
  // The phase is DERIVED from the id it was loaded for, so a service change
  // shows "loading" in the same render, never the previous service's list.
  const [loaded, setLoaded] = React.useState<{
    serviceId: string;
    phase: Phase;
  } | null>(null);
  const phase: Phase =
    loaded?.serviceId === serviceId ? loaded.phase : { kind: "loading" };
  /** Bumped after a write, so the list is read again. */
  const [reads, setReads] = React.useState(0);
  const [picked, setPicked] = React.useState<string[]>([]);
  const [current, setCurrent] = React.useState<Scenario | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  /** A poll that could not read the run; polling goes on, and this says so. */
  const [pollError, setPollError] = React.useState<string | null>(null);
  /** Bumped after a failed poll, so the poll effect schedules another. */
  const [pollRetries, setPollRetries] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    fetchScenarios(serviceId)
      .then((list) => {
        if (!cancelled)
          setLoaded({ serviceId, phase: { kind: "ready", list } });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoaded({
            serviceId,
            phase: {
              kind: "error",
              message: clientFacingError(
                err,
                "The what-ifs could not be loaded.",
              ),
            },
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [serviceId, reads]);

  // Follow a running analysis until it ends. `cancelled` is set when the
  // effect is torn down -- the admin opened another what-if, started a new
  // one, or this one changed -- so a read already in flight can never put
  // an older scenario back on screen. A failed read keeps polling and says
  // so; it never stops while "Running…" stays up.
  React.useEffect(() => {
    if (current?.run_status !== "running") return;
    const id = current.id;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchScenario(id)
        .then((next) => {
          if (cancelled) return;
          setPollError(null);
          setCurrent((prev) => (prev?.id === id ? next : prev));
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setPollError(
            clientFacingError(err, "The what-if's progress could not be read."),
          );
          setPollRetries((n) => n + 1);
        });
    }, pollMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [current, pollMs, pollRetries]);

  async function act(fn: () => Promise<void>, fallback: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(clientFacingError(err, fallback));
    } finally {
      setBusy(false);
    }
  }

  function start(removed: string[]): Promise<void> {
    return act(async () => {
      setCurrent(await createScenario(serviceId, removed));
      setReads((n) => n + 1);
    }, "The what-if could not be started.");
  }

  function run(serves: AiServes): Promise<void> {
    const s = current;
    if (!s) return Promise.resolve();
    return act(async () => {
      const started = await runScenario(s.id, serves);
      // The run HAS started. A failed read from here on is about progress,
      // never "could not be started": show it running and let the poll
      // follow it.
      try {
        setCurrent(await fetchScenario(s.id));
      } catch (err) {
        setCurrent({
          ...s,
          ai_run_id: started.run_id,
          run_status: "running",
          run_error: null,
        });
        setPollError(
          clientFacingError(
            err,
            "The AI analysis started, but its progress could not be read.",
          ),
        );
      }
    }, "The AI analysis could not be started.");
  }

  function open(id: string): Promise<void> {
    return act(async () => {
      setPollError(null);
      setCurrent(await fetchScenario(id));
    }, "The what-if could not be opened.");
  }

  /** Back to the picker: what "Start a new what-if" in the 409 copy names. */
  function startNew(): void {
    setCurrent(null);
    setPicked([]);
    setError(null);
    setPollError(null);
  }

  function discard(): Promise<void> {
    const s = current;
    if (!s) return Promise.resolve();
    return act(async () => {
      setCurrent(await discardScenario(s.id));
      setReads((n) => n + 1);
    }, "The what-if could not be discarded.");
  }

  function toggle(tool: string): void {
    setPicked((p) =>
      p.includes(tool) ? p.filter((t) => t !== tool) : [...p, tool],
    );
  }

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-line p-4"
      data-testid="attack-scenario-panel"
      aria-labelledby="attack-scenario-title"
    >
      <h3
        id="attack-scenario-title"
        className="text-base font-semibold text-ink-primary"
      >
        ATT&amp;CK what-if
      </h3>
      <p className="text-sm text-ink-secondary">
        {
          "Try a change to the client's tools and see how ATT&CK coverage would change. Nothing changes on the assessment or the client's view."
        }
      </p>

      {phase.kind === "loading" ? (
        <p className="text-sm text-ink-secondary">Loading…</p>
      ) : null}
      {phase.kind === "error" ? (
        <p role="alert" className="text-sm text-status-danger-fg">
          {phase.message}
        </p>
      ) : null}

      {phase.kind === "ready" && phase.list.base === null ? (
        <p data-testid="attack-scenario-no-base" className="text-sm">
          {NO_BASE}
        </p>
      ) : null}

      {phase.kind === "ready" && phase.list.base !== null && !current ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-ink-secondary">
            Compared with the last confirmed assessment: version{" "}
            {phase.list.base.version}, approved{" "}
            {approvedText(phase.list.base.approved_at)}.
          </p>
          <fieldset className="flex flex-col gap-1">
            <legend className="text-sm font-semibold">Tools to remove</legend>
            {phase.list.base.tools.map((tool) => (
              <label key={tool} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={picked.includes(tool)}
                  onChange={() => toggle(tool)}
                />
                {tool}
              </label>
            ))}
          </fieldset>
          <div>
            <button
              type="button"
              disabled={busy}
              onClick={() => void start(picked)}
              className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-60"
            >
              Continue
            </button>
          </div>
        </div>
      ) : null}

      {phase.kind === "ready" && !current ? (
        <ScenarioList
          scenarios={phase.list.scenarios.filter(
            (x) => x.state !== "discarded",
          )}
          busy={busy}
          onOpen={(id) => void open(id)}
        />
      ) : null}

      {current ? (
        <>
          <ScenarioView
            s={current}
            busy={busy}
            onRun={(serves) => void run(serves)}
            onDiscard={() => void discard()}
            onRunAgain={() => void start(current.removed)}
          />
          {/* Always offered: a running what-if stays reachable from the
              list, and its run goes on without this page. */}
          <div>
            <button
              type="button"
              disabled={busy}
              onClick={startNew}
              className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-60"
            >
              Start a new what-if
            </button>
          </div>
        </>
      ) : null}

      {pollError ? (
        <p
          role="alert"
          data-testid="attack-scenario-poll-error"
          className="text-sm text-status-warning-fg"
        >
          {pollError}
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          data-testid="attack-scenario-error"
          className="text-sm text-status-danger-fg"
        >
          {error}
        </p>
      ) : null}
    </section>
  );
}

/** NEW copy: the heading, each row's line and its control. */
function ScenarioList({
  scenarios,
  busy,
  onOpen,
}: {
  scenarios: ScenarioSummary[];
  busy: boolean;
  onOpen: (id: string) => void;
}): JSX.Element | null {
  if (scenarios.length === 0) return null;
  return (
    <div className="flex flex-col gap-1" data-testid="attack-scenario-list">
      <h4 className="text-sm font-semibold">What-ifs on this service</h4>
      <ul className="flex flex-col gap-1">
        {scenarios.map((x) => (
          <li key={x.id} className="flex items-center gap-2 text-sm">
            <span>
              {x.removed.join(", ")} (compared with version {x.base_version})
            </span>
            <button
              type="button"
              disabled={busy}
              onClick={() => onOpen(x.id)}
              className="rounded-md border border-line px-2 py-0.5 text-sm disabled:opacity-60"
            >
              Open
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ScenarioView({
  s,
  busy,
  onRun,
  onDiscard,
  onRunAgain,
}: {
  s: Scenario;
  busy: boolean;
  onRun: (serves: AiServes) => void;
  onDiscard: () => void;
  onRunAgain: () => void;
}): JSX.Element {
  const higher = s.scored_higher ?? 0;
  const notReassessed = s.not_reassessed ?? [];
  // Runnable: not set aside, not stale, and no analysis standing. A FAILED
  // run wrote nothing, and the api accepts running the same what-if again.
  const runnable =
    s.state !== "discarded" &&
    !s.stale &&
    (s.run_status === null || s.run_status === "failed");
  return (
    <div className="flex flex-col gap-3" data-testid="attack-scenario">
      <p className="text-sm">
        <span className="font-semibold">Tools to remove:</span>{" "}
        {s.removed.join(", ")}
      </p>
      <p className="text-sm" data-testid="attack-scenario-affected">
        {affectedLine(s.affected_codes.length)}
      </p>

      {s.stale ? (
        <div
          className="text-sm text-status-warning-fg"
          data-testid="attack-scenario-stale"
        >
          <p>
            This what-if was compared with version {s.base_version}. A newer
            assessment has been confirmed since; run it again to compare with
            that one.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={onRunAgain}
            className="mt-1 rounded-md border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-60"
          >
            Run it again
          </button>
        </div>
      ) : null}

      {s.run_status === "failed" ? (
        <p
          role="alert"
          className="text-sm text-status-danger-fg"
          data-testid="attack-scenario-run-failed"
        >
          {s.run_error?.message ?? "The AI analysis did not finish."}
        </p>
      ) : null}

      {runnable && !s.analysis_available ? (
        <p className="text-sm" data-testid="attack-scenario-unavailable">
          {UNAVAILABLE}
        </p>
      ) : null}

      {runnable && s.analysis_available ? (
        <RunAiGuard onProceed={onRun}>
          {({ onClick, statusUnknown }) => (
            <div>
              <button
                type="button"
                onClick={onClick}
                disabled={busy || statusUnknown}
                className="rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-ink-on-accent hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Run AI analysis on these changes
              </button>
            </div>
          )}
        </RunAiGuard>
      ) : null}

      {s.run_status === "running" ? (
        <p className="text-sm text-ink-secondary" aria-live="polite">
          Running…
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Rollup heading="Coverage today" r={s.today} testId="scenario-today" />
        {s.after ? (
          <Rollup
            heading="With these changes"
            r={s.after}
            testId="scenario-after"
          />
        ) : null}
      </div>

      {s.after ? (
        <>
          <p className="text-sm text-ink-secondary">
            Only the techniques these tools appear on were re-assessed. Every
            other technique is as the last confirmed assessment has it.
          </p>
          {higher > 0 ? (
            <p
              role="alert"
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-higher"
            >
              {scoredHigherLine(higher)}
            </p>
          ) : null}
          {notReassessed.length > 0 ? (
            <p
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-not-reassessed"
            >
              {notReassessedLine(notReassessed.length)}
            </p>
          ) : null}
          {dropLines(s.dropped ?? {}).map((line) => (
            <p
              key={line}
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-dropped"
            >
              {line}
            </p>
          ))}
          {s.differences.length > 0 ? (
            <table className="text-sm" data-testid="attack-scenario-diffs">
              <thead>
                <tr>
                  <th className="text-left">Technique</th>
                  <th className="text-left">Today</th>
                  <th className="text-left">With these changes</th>
                </tr>
              </thead>
              <tbody>
                {s.differences.map((d) => (
                  <tr key={d.technique_code}>
                    <td>{d.technique_code}</td>
                    <td>{d.today ?? "not scored"}</td>
                    <td>
                      {d.after ?? "not scored"}
                      {d.scored_higher ? (
                        <span
                          className="ml-2 font-semibold text-status-warning-fg"
                          data-testid="attack-scenario-diff-higher"
                        >
                          Scores higher
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </>
      ) : null}

      {s.state !== "discarded" ? (
        <div>
          <button
            type="button"
            disabled={busy}
            onClick={onDiscard}
            className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-60"
          >
            Discard this what-if
          </button>
        </div>
      ) : null}
    </div>
  );
}
