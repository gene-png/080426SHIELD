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
/**
 * One attempt at refreshing one source. Both writes are NO-OPS once a later
 * attempt on the same source has begun.
 *
 * This is the guard, and it lives here rather than at the call sites because
 * that is exactly where it went missing. The review of `158c2af` found the
 * sequence check present in ONE function (`TechDebtWorkspace.refreshOverlap`,
 * where the original finding was reported) and absent from every other write
 * -- three workspaces captured no sequence at all, and even in Tech Debt the
 * deliverable branch sat outside its own file's guard. Same shape as the
 * single-slot defect one level up: a rule applied at four sites diverges at
 * four sites.
 *
 * Concretely, what it stops: two answer edits ~200ms apart. Refresh #2
 * succeeds and clears; refresh #1 then rejects and pins a permanent
 * "the figures shown may be out of date" over figures that are up to date.
 * The mirror is equally live -- a stale SUCCESS clearing a current failure.
 */
export type RefreshAttempt = {
  /** True once a later attempt on this source has begun. */
  superseded: () => boolean;
  /** Record that this source failed -- unless this attempt is superseded. */
  note: (message: string) => void;
  /** Withdraw this source's message -- unless this attempt is superseded. */
  clear: () => void;
};

export type RefreshFailures = {
  /** Live failure messages, in the order their sources first failed. */
  messages: string[];
  /**
   * Start an attempt on `source`. EVERY write goes through the returned
   * token; there is deliberately no unsequenced `note`/`clear` on this
   * object, because an optional guard is one a caller can forget and three
   * of four callers did.
   *
   * **CALL THIS BEFORE ANY `await`, at the top of the refresh function.**
   *
   * The token's ordering is the order `begin` was CALLED. Mint it after an
   * await and the tokens are ordered by when those awaits RESOLVED, which is
   * the opposite of what the guard needs: a refresh invoked FIRST whose
   * earlier fetch is slow mints the LATER token, owns the slot, and writes
   * over the newer refresh -- verbatim the defect the token replaced.
   *
   * Not hypothetical. `TechDebtWorkspace.refreshOverlap` minted below
   * `await fetchOverlapAnalysis`, in a function whose own comment says those
   * fetches "can resolve out of order", so the first version of this fix was
   * WEAKER than the hand-rolled `seq` it replaced -- that captured at entry.
   * Caught by the third adversarial round, not by the tests: the existing one
   * mocks the first fetch with `mockResolvedValue`, so only the second ever
   * varied in timing and the inversion could not arise.
   */
  begin: (source: string) => RefreshAttempt;
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

  // Latest attempt number per source. A ref, not state: it must be readable
  // synchronously by an in-flight attempt deciding whether it still owns the
  // slot, and bumping it must not re-render.
  const seqBySource = React.useRef<Record<string, number>>({});

  const begin = React.useCallback(
    (source: string): RefreshAttempt => {
      const mine = (seqBySource.current[source] ?? 0) + 1;
      seqBySource.current[source] = mine;
      const owns = () => mine === (seqBySource.current[source] ?? 0);
      return {
        superseded: () => !owns(),
        note: (message: string) => {
          if (owns()) note(source, message);
        },
        clear: () => {
          if (owns()) clear(source);
        },
      };
    },
    [note, clear],
  );

  const messages = React.useMemo(() => Object.values(bySource), [bySource]);

  // Memoized so the returned object is stable while nothing has failed.
  // `note` and `clear` are stable on their own, which is what the callers
  // actually put in their dependency arrays -- a `refreshScoreAndGap` that
  // depended on the whole object would be rebuilt every time an UNRELATED
  // source failed, which is the clobbering shape one level up.
  return React.useMemo(() => ({ messages, begin }), [messages, begin]);
}
