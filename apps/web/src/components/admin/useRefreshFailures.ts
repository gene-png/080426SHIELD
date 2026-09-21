import * as React from "react";

/**
 * SUPPLEMENTARY fetch failures, keyed by SOURCE (#292).
 *
 * A workspace runs several side fetches -- score, gap, interview prompts, the
 * latest deliverable, an overlap plan. Each is non-blocking: the workspace
 * itself loaded, and `loadError` is the blocking card that says it did not.
 * What these needed was a way to say "this panel is stale because a request
 * failed" rather than leaving it `null`, which is byte-identical to
 * still-loading.
 *
 * **THE KEY IS THE WHOLE POINT, and a single `string | null` was wrong in two
 * OPPOSITE directions at once.** Both were found by the adversarial review of
 * `d25caf7`, and neither is a race:
 *
 *   - **Clobbering.** `CsfWorkspace` cleared the one slot on any success, so a
 *     failed interview-prompt fetch was wiped by the score/gap refresh three
 *     statements later, every time, on the ordinary path. The consultant was
 *     left looking at 106 subcategories showing no prompts with nothing on
 *     screen to say the prompts had failed to load -- exactly the state the
 *     sentence was written to deny.
 *   - **Never clearing.** The other three workspaces never cleared at all, so
 *     one transient failure pinned a permanent "may be out of date" warning
 *     over figures that had since refreshed correctly.
 *
 * One slot cannot hold two facts, and clearing it is either too eager or never
 * right. Keyed by source, each fetch owns its own line: a success clears only
 * what that fetch had said, and the banner is DERIVED from the record rather
 * than maintained alongside it. `CLAUDE.md`: prefer a derivation over a
 * synchronization -- a derived value cannot be out of sync, a synchronized one
 * merely is not, right now.
 *
 * `note` and `clear` both return the previous object when nothing changes, so
 * a repeated failure or a clear of something that never failed does not
 * re-render.
 */
export type RefreshFailures = {
  /** Live failure messages, in the order their sources first failed. */
  messages: string[];
  /** Record that `source` failed. Replaces whatever that source said before. */
  note: (source: string, message: string) => void;
  /** Withdraw `source`'s message, if it had one. Touches no other source. */
  clear: (source: string) => void;
};

export function useRefreshFailures(): RefreshFailures {
  const [bySource, setBySource] = React.useState<Record<string, string>>({});

  const note = React.useCallback((source: string, message: string) => {
    setBySource((prev) =>
      prev[source] === message ? prev : { ...prev, [source]: message },
    );
  }, []);

  const clear = React.useCallback((source: string) => {
    setBySource((prev) => {
      if (!(source in prev)) return prev;
      const next = { ...prev };
      delete next[source];
      return next;
    });
  }, []);

  const messages = React.useMemo(() => Object.values(bySource), [bySource]);

  // Memoized so the returned object is stable while nothing has failed.
  // `note` and `clear` are stable on their own, which is what the callers
  // actually put in their dependency arrays -- a `refreshScoreAndGap` that
  // depended on the whole object would be rebuilt every time an UNRELATED
  // source failed, which is the clobbering shape one level up.
  return React.useMemo(
    () => ({ messages, note, clear }),
    [messages, note, clear],
  );
}
