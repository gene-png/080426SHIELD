"use client";

import * as React from "react";

import { RunAiGuard } from "@/components/admin/RunAiGuard";
import { fetchAiStatus } from "@/lib/admin/client";
import { clientFacingError } from "@/lib/describe-save-error";
import { outsideAssessedText } from "@/lib/attack/outsideAssessed";
import {
  createScenario,
  discardScenario,
  fetchScenario,
  fetchScenarios,
  parseChange,
  runScenario,
} from "@/lib/attack/scenarios";

import type { AiServes } from "@/lib/aiRuns/types";
import type {
  AddedTool,
  ParsedChange,
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

/** The advisor's (ii) copy, 08:57Z, byte for byte; shown only above zero. */
function addedToolsLine(n: number): string {
  return n === 1
    ? "1 tool was added to the client's list, or brought into scope, after the last confirmed assessment was approved. It was offered to the AI and may have taken over a removed tool's role."
    : `${n} tools were added to the client's list, or brought into scope, after the last confirmed assessment was approved. They were offered to the AI and may have taken over a removed tool's role.`;
}

/** The advisor's (b2) copy for a count that could not be checked (null). */
const ADDED_UNCHECKED =
  "Whether tools were added since the last confirmed assessment could not be checked for this client's list.";

/** B9 (14:58Z): techniques only an added tool could change. */
function addedAffectedLine(n: number): string {
  return n === 1
    ? "1 technique has a gap an added tool could fill, and will be re-assessed."
    : `${n} techniques have a gap an added tool could fill, and will be re-assessed.`;
}

/** B11 (14:58Z): a result, not a warning. */
function higherWithAddedLine(n: number): string {
  return n === 1
    ? "1 technique would score higher with the added tools."
    : `${n} techniques would score higher with the added tools.`;
}

/** B14 (14:58Z), always beside the results when tools were added. */
const ADDED_IN_PLACE =
  "Tools you added count as in place. The AI judged what they cover from the name and functions you entered; they are not on the client's list.";

/**
 * The techniques a failed batch left with the removal alone. With nothing
 * removed (an addition-only what-if) there is no removal to show, so they show
 * the last confirmed assessment unchanged (NEW copy, #818 review F9).
 */
function notReassessedLine(n: number, anyRemoved: boolean): string {
  if (!anyRemoved) {
    return n === 1
      ? "1 technique could not be re-assessed because the AI did not answer for it. It shows the last confirmed assessment unchanged."
      : `${n} techniques could not be re-assessed because the AI did not answer for them. They show the last confirmed assessment unchanged.`;
  }
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
  const notAdded = dropped.tool_not_added ?? 0;
  const notDeclared = dropped.function_not_declared ?? 0;
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
  // B13 (14:58Z).
  if (notAdded > 0)
    lines.push(
      `${notAdded} AI ${plural(notAdded, "suggestion was", "suggestions were")} set aside because ${plural(notAdded, "it", "they")} credited one of the client's tools where only an added tool was asked about.`,
    );
  // The advisor, 16:00Z (#818 F6).
  if (notDeclared > 0)
    lines.push(
      `${notDeclared} AI ${plural(notDeclared, "suggestion was", "suggestions were")} set aside because ${plural(notDeclared, "it", "they")} credited an added tool with something you did not choose for it.`,
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
      {r.awaiting_review_text ? (
        <p className="text-sm text-status-warning-fg">
          {r.awaiting_review_text}
        </p>
      ) : null}
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
  // The picker belongs to the service it was filled for: DERIVED from the
  // id, so a service change shows an empty picker in the same render and a
  // late writer for the old service lands nowhere visible (#824 review, B3).
  const [picker, setPicker] = React.useState<{
    serviceId: string;
    picked: string[];
    adding: Draft[];
  }>({ serviceId, picked: [], adding: [] });
  const mine = picker.serviceId === serviceId;
  const picked = mine ? picker.picked : NONE_PICKED;
  /** Slice B: the tools to add, as the admin is typing them. */
  const adding = mine ? picker.adding : NONE_ADDING;
  const setPicked = React.useCallback(
    (next: string[] | ((prev: string[]) => string[])) =>
      setPicker((p) => {
        const same = p.serviceId === serviceId;
        const prev = same ? p.picked : NONE_PICKED;
        return {
          serviceId,
          picked: typeof next === "function" ? next(prev) : next,
          adding: same ? p.adding : NONE_ADDING,
        };
      }),
    [serviceId],
  );
  const setAdding = React.useCallback(
    (next: Draft[] | ((prev: Draft[]) => Draft[])) =>
      setPicker((p) => {
        const same = p.serviceId === serviceId;
        const prev = same ? p.adding : NONE_ADDING;
        return {
          serviceId,
          picked: same ? p.picked : NONE_PICKED,
          adding: typeof next === "function" ? next(prev) : next,
        };
      }),
    [serviceId],
  );
  /** A chat parse is in flight: the picker is held still until it lands. */
  const [chatBusy, setChatBusy] = React.useState(false);
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

  function start(removed: string[], added: AddedTool[]): Promise<void> {
    return act(async () => {
      setCurrent(await createScenario(serviceId, removed, added));
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
    setAdding([]);
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
          {(phase.list.base.citations_outside_subset ?? 0) > 0 ? (
            // #851: the workspace's disclosure, for the base. Copy approved (#736, 6024072042).
            <p
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-base-outside-subset"
            >
              {phase.list.base.citations_outside_subset === 1
                ? "1 technique row in this assessment credits a tool that is not in the client's security tool list, so today's figure may count a tool the client does not use."
                : `${phase.list.base.citations_outside_subset} technique rows in this assessment credit a tool that is not in the client's security tool list, so today's figure may count tools the client does not use.`}
            </p>
          ) : null}
          <ChatBox
            key={serviceId}
            serviceId={serviceId}
            onBusy={setChatBusy}
            onProposal={(proposal) => {
              // MERGE, never replace (#824 review, B2): what the admin has
              // ticked or typed stays; an empty proposal changes nothing.
              setPicked((prev) => [
                ...prev,
                ...proposal.removed.filter((t) => !prev.includes(t)),
              ]);
              setAdding((prev) => [
                ...prev,
                ...proposal.added
                  .filter(
                    (name) =>
                      !prev.some(
                        (d) =>
                          d.name.trim().toLowerCase() === name.toLowerCase(),
                      ),
                  )
                  .map((name) => ({
                    name,
                    vendor: "",
                    category: "",
                    functions: [],
                    fromChat: true,
                  })),
              ]);
            }}
          />
          <fieldset className="flex flex-col gap-1" disabled={chatBusy}>
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
          <AddToolsFieldset
            drafts={adding}
            onChange={setAdding}
            disabled={chatBusy}
          />
          <div>
            <button
              type="button"
              disabled={busy || chatBusy}
              onClick={() => void start(picked, adding.map(toAddedTool))}
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
            onRunAgain={() => void start(current.removed, current.added ?? [])}
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

/**
 * Slice C (approved 18:32Z, copy C1-C8): the chat box. The api's matcher, by
 * code and with no AI, PROPOSES a change list that fills in the picker below;
 * nothing is created or run until Continue and Run, which stay the only paths.
 */
function ChatBox({
  serviceId,
  onProposal,
  onBusy,
}: {
  serviceId: string;
  onProposal: (proposal: ParsedChange) => void;
  onBusy: (busy: boolean) => void;
}): JSX.Element {
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<ParsedChange | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  // A response is applied only while this mount is the one that asked: the
  // panel remounts the box per service, so a parse that lands after a service
  // change is dropped (#824 review, B3). One parse at a time: Fill is disabled
  // while one is in flight, and the picker is held still (`onBusy`).
  const latest = React.useRef(0);
  React.useEffect(() => {
    const mounted = latest;
    return () => {
      mounted.current = -1;
      onBusy(false);
    };
  }, [onBusy]);

  async function fill(): Promise<void> {
    const mine = ++latest.current;
    setBusy(true);
    onBusy(true);
    setError(null);
    try {
      // #504, as RunAiGuard decides it: the AI may read the text only while
      // it is ready. Not ready sends "offline", and so does a status that
      // cannot be read, which acknowledges nothing: the API then answers with
      // the list matcher alone, and the text is not sent to the AI.
      const serves: AiServes = await fetchAiStatus().then(
        (status) => (status.ready ? "live" : "offline"),
        () => "offline",
      );
      const proposal = await parseChange(serviceId, text, serves);
      if (latest.current !== mine) return;
      setResult(proposal);
      onProposal(proposal);
    } catch (err) {
      if (latest.current !== mine) return;
      setResult(null);
      setError(
        clientFacingError(
          err,
          "The description could not be checked. Try again.",
        ),
      );
    } finally {
      if (latest.current === mine) {
        setBusy(false);
        onBusy(false);
      }
    }
  }

  const matched =
    result !== null && result.removed.length + result.added.length > 0;
  return (
    <div className="flex flex-col gap-1" data-testid="attack-scenario-chat">
      <label className="flex flex-col gap-1 text-sm font-semibold">
        Describe the change
        <textarea
          className="rounded border border-line p-1 font-normal"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      <p className="text-sm text-ink-secondary">
        {'For example "retire X and Y" or "swap X for Z".'}
      </p>
      <div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void fill()}
          className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-60"
        >
          Fill in the change list
        </button>
      </div>
      {matched ? (
        <p className="text-sm" data-testid="attack-scenario-chat-filled">
          {result?.source === "ai"
            ? // N1, approved verbatim (16:40Z, #802 comment 5982109105).
              "The change list below was filled in by the AI from your description. Check it before you continue."
            : "The change list below was filled in from your description. Check it before you continue."}
        </p>
      ) : null}
      {result?.left_out_message ? (
        <p
          className="text-sm text-status-warning-fg"
          data-testid="attack-scenario-chat-left-out"
        >
          {result.left_out_message}
        </p>
      ) : null}
      {result?.note ? (
        <p
          className="text-sm text-status-warning-fg"
          data-testid="attack-scenario-chat-note"
        >
          {result.note}
        </p>
      ) : null}
      {result !== null && !matched ? (
        <p
          className="text-sm text-status-warning-fg"
          data-testid="attack-scenario-chat-nothing"
        >
          Nothing in your description matched a change. Pick the tools from the
          list instead.
        </p>
      ) : null}
      {(result?.not_understood ?? []).map((n, i) => (
        <p
          key={i}
          className="text-sm text-status-warning-fg"
          data-testid="attack-scenario-chat-not-understood"
        >
          {n.message}
        </p>
      ))}
      {error ? (
        <p
          role="alert"
          className="text-sm text-status-danger-fg"
          data-testid="attack-scenario-chat-error"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

const NONE_PICKED: string[] = [];
const NONE_ADDING: Draft[] = [];

/** A tool to add, as typed: every field a string until it is sent. */
interface Draft {
  name: string;
  vendor: string;
  category: string;
  functions: AddedTool["security_functions"];
  /** Filled in from the chat box (slice C): C9 asks for its functions. */
  fromChat?: boolean;
}

const FUNCTIONS: [AddedTool["security_functions"][number], string][] = [
  ["detect", "Detect"],
  ["prevent", "Prevent"],
  ["respond", "Respond"],
];

/**
 * A listed what-if's tools. A removal-only what-if reads as slice A's approved
 * row; one that adds tools labels both halves with the approved change-list
 * labels, so "EDR Tool, XDR Suite" never leaves the reader guessing which went
 * and which came (NEW row text, #818 review F5).
 */
function rowTools(x: { removed: string[]; added?: string[] }): string {
  const added = x.added ?? [];
  if (added.length === 0) return x.removed.join(", ");
  const parts = [];
  if (x.removed.length > 0)
    parts.push(`Tools to remove: ${x.removed.join(", ")}`);
  parts.push(`Tools to add: ${added.join(", ")}`);
  return parts.join("; ");
}

function toAddedTool(d: Draft): AddedTool {
  return {
    name: d.name,
    vendor: d.vendor.trim() ? d.vendor : null,
    category: d.category.trim() ? d.category : null,
    security_functions: d.functions,
  };
}

/** B1-B3 (14:58Z). The api validates every field and refuses in its own words. */
function AddToolsFieldset({
  drafts,
  onChange,
  disabled = false,
}: {
  drafts: Draft[];
  onChange: (next: Draft[]) => void;
  /** Held still while a chat parse is in flight (#824 review, B3). */
  disabled?: boolean;
}): JSX.Element {
  function update(i: number, patch: Partial<Draft>): void {
    onChange(drafts.map((d, k) => (k === i ? { ...d, ...patch } : d)));
  }
  return (
    <fieldset
      className="flex flex-col gap-2"
      data-testid="attack-scenario-add"
      disabled={disabled}
    >
      <legend className="text-sm font-semibold">Tools to add</legend>
      {drafts.map((d, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-1">
            Name
            <input
              className="rounded border border-line px-1"
              value={d.name}
              onChange={(e) => update(i, { name: e.target.value })}
            />
          </label>
          <label className="flex items-center gap-1">
            Vendor (optional)
            <input
              className="rounded border border-line px-1"
              value={d.vendor}
              onChange={(e) => update(i, { vendor: e.target.value })}
            />
          </label>
          <label className="flex items-center gap-1">
            Category (optional)
            <input
              className="rounded border border-line px-1"
              value={d.category}
              onChange={(e) => update(i, { category: e.target.value })}
            />
          </label>
          <span>What it does:</span>
          {FUNCTIONS.map(([value, label]) => (
            <label key={value} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={d.functions.includes(value)}
                onChange={() =>
                  update(i, {
                    functions: d.functions.includes(value)
                      ? d.functions.filter((f) => f !== value)
                      : FUNCTIONS.map(([v]) => v).filter(
                          (v) => v === value || d.functions.includes(v),
                        ),
                  })
                }
              />
              {label}
            </label>
          ))}
          <button
            type="button"
            className="rounded-md border border-line px-2 py-0.5"
            onClick={() => onChange(drafts.filter((_, k) => k !== i))}
          >
            Remove this tool
          </button>
          {d.fromChat && d.functions.length === 0 ? (
            <p
              className="basis-full text-sm text-status-warning-fg"
              data-testid="attack-scenario-chat-functions"
            >
              {`Choose what ${d.name} does before you continue.`}
            </p>
          ) : null}
        </div>
      ))}
      <div>
        <button
          type="button"
          className="rounded-md border border-line px-2 py-0.5 text-sm"
          onClick={() =>
            onChange([
              ...drafts,
              { name: "", vendor: "", category: "", functions: [] },
            ])
          }
        >
          Add a tool
        </button>
      </div>
    </fieldset>
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
              {rowTools(x)} (compared with version {x.base_version})
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
  // Slice B: absent on a what-if read before slice B shipped.
  const added = s.added ?? [];
  const notReassessed = s.not_reassessed ?? [];
  // (b2): techniques credited to an added tool whose status did not move, so
  // the differences table cannot mark them.
  const changed = new Set(s.differences.map((d) => d.technique_code));
  const creditedUnchanged = s.techniques
    .filter(
      (t) =>
        t.credited_added_tools.length > 0 && !changed.has(t.technique_code),
    )
    .map((t) => t.technique_code);
  // Runnable: not set aside, not stale, and no result standing. A FAILED
  // run wrote nothing, and the api accepts running the same what-if again --
  // but a result can stand beside a failed run (#815 round 2: a later run
  // that found the result already written), so the result decides, not the
  // run's status.
  const runnable =
    s.state !== "discarded" &&
    !s.stale &&
    s.after === null &&
    (s.run_status === null || s.run_status === "failed");
  return (
    <div className="flex flex-col gap-3" data-testid="attack-scenario">
      {s.removed.length > 0 ? (
        <p className="text-sm">
          <span className="font-semibold">Tools to remove:</span>{" "}
          {s.removed.join(", ")}
        </p>
      ) : null}
      {added.length > 0 ? (
        <p className="text-sm" data-testid="attack-scenario-added-tools">
          <span className="font-semibold">Tools to add:</span>{" "}
          {added.map((t) => t.name).join(", ")}
        </p>
      ) : null}
      {added.length === 0 ? (
        <p className="text-sm" data-testid="attack-scenario-affected">
          {affectedLine(s.affected_codes.length)}
        </p>
      ) : (
        <>
          {s.affected_by_removal > 0 ? (
            <p className="text-sm" data-testid="attack-scenario-affected">
              {affectedLine(s.affected_by_removal)}
            </p>
          ) : null}
          {s.affected_by_addition_only > 0 ? (
            <p className="text-sm" data-testid="attack-scenario-affected-added">
              {addedAffectedLine(s.affected_by_addition_only)}
            </p>
          ) : null}
        </>
      )}

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
          {added.length === 0 ? (
            <p className="text-sm text-ink-secondary">
              Only the techniques these tools appear on were re-assessed. Every
              other technique is as the last confirmed assessment has it.
            </p>
          ) : (
            <>
              <p className="text-sm text-ink-secondary">
                Only the techniques these changes could affect were re-assessed.
                Every other technique is as the last confirmed assessment has
                it.
              </p>
              <p
                className="text-sm"
                data-testid="attack-scenario-added-in-place"
              >
                {ADDED_IN_PLACE}
              </p>
              {(s.higher_with_added ?? 0) > 0 ? (
                <p
                  className="text-sm"
                  data-testid="attack-scenario-higher-added"
                >
                  {higherWithAddedLine(s.higher_with_added ?? 0)}
                </p>
              ) : null}
            </>
          )}
          {higher > 0 ? (
            <p
              role="alert"
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-higher"
            >
              {scoredHigherLine(higher)}
            </p>
          ) : null}
          {s.tools_added_since_base === null ? (
            <p
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-added-unchecked"
            >
              {ADDED_UNCHECKED}
            </p>
          ) : s.tools_added_since_base > 0 ? (
            <p
              role="alert"
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-added"
            >
              {addedToolsLine(s.tools_added_since_base)}
            </p>
          ) : null}
          {creditedUnchanged.length > 0 ? (
            <p
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-added-unchanged"
            >
              Also credited to an added tool, with no change in status:{" "}
              {creditedUnchanged.join(", ")}.
            </p>
          ) : null}
          {notReassessed.length > 0 ? (
            <p
              className="text-sm text-status-warning-fg"
              data-testid="attack-scenario-not-reassessed"
            >
              {notReassessedLine(notReassessed.length, s.removed.length > 0)}
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
                      {d.credited_tool_you_added ? (
                        <span
                          className="ml-2 font-semibold"
                          data-testid="attack-scenario-diff-you-added"
                        >
                          Credited to a tool you added
                        </span>
                      ) : null}
                      {d.credited_added_tool ? (
                        <span
                          className="ml-2 font-semibold text-status-warning-fg"
                          data-testid="attack-scenario-diff-added"
                        >
                          Credited to an added tool
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
