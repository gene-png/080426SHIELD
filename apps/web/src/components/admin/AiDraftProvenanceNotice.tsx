import type { JSX } from "react";

/**
 * Standing notice that the accounting panel above it contains AI-drafted text
 * which is informed by client-submitted input (issue #68).
 *
 * WHY THIS EXISTS. The run-AI accounting itemizes rejected suggestions and
 * echoes back, verbatim, the capability code or field name the MODEL wrote.
 * That text is transitively client-controlled: a client-role user's answer
 * `notes` go into the egress payload unchanged, so a note can shape what the
 * model emits, and the model's output then renders in the panel a consultant
 * uses to judge whether the draft is trustworthy — in the application's own
 * typeface and voice, with nothing marking it as untrusted.
 *
 * Attribution-tracing — highlighting which specific substrings originated
 * where — would be real engineering and is not what this is. This is a
 * compensating control: it removes the ambiguity about the panel's *provenance*
 * without pretending to resolve any individual string.
 *
 * DESIGN CONSTRAINTS, deliberately:
 *
 * - **Its own component, rendered as a SIBLING of the accounting panel.** It
 *   does not live inside `ZtRunAiAccounting`, and touches none of that
 *   component's severity logic, which took five adversarial rounds and a
 *   from-scratch state matrix to stabilise. A "small" addition threaded through
 *   that state is how a sixth non-convergent round starts by accident.
 * - **No live region, no `role`.** Purely static informational copy. Adding
 *   another announced region here would make the panel's announcement story
 *   worse, not better — see #69, which is already open on exactly that.
 * - **Not dismissable.** No state, no control, no persistence. A notice a
 *   consultant can turn off is one they will turn off on day two, and the risk
 *   it describes is present on every run.
 * - **Rendered on ZT and CSF alike.** Both prompts carry client-submitted
 *   input (ZT answer notes, CSF interview answers), so the vector is identical;
 *   covering one would be an unstated exemption.
 */
export function AiDraftProvenanceNotice(): JSX.Element {
  return (
    <p className="rounded border border-ink-tertiary/30 px-3 py-2 text-xs text-ink-tertiary">
      <span className="font-semibold">AI-drafted.</span> The values and any
      quoted text above were produced by the model and are informed by
      client-submitted input. Treat them as a draft to verify, not as findings.
    </p>
  );
}
