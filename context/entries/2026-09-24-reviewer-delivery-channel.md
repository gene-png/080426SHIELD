# 2026-09-24: the reviewer delivers through the harness's named tool first

`.claude/agents/adversarial-reviewer.md` said to deliver the report with
`SendMessage` and named no other channel. Four reviewers dispatched through
the Agent tool on 2026-09-24 were told by the harness that only its hand-back
call reaches the caller. Each used the hand-back, each report arrived, and each
flagged the contradiction.

The rule that matters is unchanged: finish with a tool call, never plain text.
Only the tool's name moved, and it now comes from the dispatch first, falling
back to `SendMessage`. The reviewer names the channel it used in the report's
opening line. Any disagreement about the channel is a run-finding: between
the file, its injected copy, the dispatcher's prose and the tool the system
names, or a tool that changed its name. Step 0 now says the `tools:` line is a
floor, because the harness adds its hand-back tool without the line naming it.
The four reviews are recorded in PR #545's audit section and on the
`fix/literal-pattern-typed-empty` branch.

This is a live instance of #215, where agent definitions go stale against the
world with nothing checking them. The owner labelled #215 mvp-blocking and
tier-3 the same day.
