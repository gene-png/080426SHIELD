# 2026-09-24: the reviewer delivers through the harness's named tool first

`.claude/agents/adversarial-reviewer.md` said to deliver the report with
`SendMessage` and named no other channel. Four reviewers dispatched through
the Agent tool on 2026-09-24 were told by the harness that only its hand-back
call reaches the caller. Each used the hand-back, each report arrived, and each
flagged the contradiction.

The rule that matters is unchanged: finish with a tool call, never plain text.
Only the tool's name moved, and it now comes from the dispatch first, falling
back to `SendMessage`. The reviewer names the channel it used, and a
disagreement between the file and the dispatch is a run-finding.

This is a live instance of #215, where agent definitions go stale against the
world with nothing checking them. The owner labelled #215 mvp-blocking and
tier-3 the same day.
