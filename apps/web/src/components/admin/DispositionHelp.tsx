import type { JSX } from "react";

// #642. Every statement here was checked against the API's readers of
// `CapabilityItem.disposition` at c39e6c8 (the answer is on the issue): only
// Tech Debt's own surfaces read it, and only `cut` moves a number. If a
// disposition ever starts feeding another service, this copy is wrong.
const DISPOSITIONS: ReadonlyArray<{ label: string; effect: string }> = [
  {
    label: "Undecided",
    effect:
      "No recommendation yet. Counted under Undecided in the consolidation plan.",
  },
  {
    label: "Keep",
    effect:
      "Recommend keeping the tool. Counted under Keep; no figure changes.",
  },
  {
    label: "Consolidate",
    effect:
      "Recommend folding the tool into another one. Counted under Consolidate; its cost is not counted as savings.",
  },
  {
    label: "Cut",
    effect:
      "Recommend retiring the tool. Its annual cost is added to the estimated annual savings. If a cut row has no cost, the savings figure is shown as a lower bound.",
  },
];

/** Explains the Disposition column in the step-2 table. */
export function DispositionHelp(): JSX.Element {
  return (
    <details
      className="rounded-lg border border-border-subtle bg-surface-sunken px-3 py-2 text-sm"
      data-testid="disposition-help"
    >
      <summary className="cursor-pointer font-medium text-ink-primary">
        What the dispositions mean
      </summary>
      <p className="mt-2 text-ink-secondary">
        The disposition is this assessment&apos;s recommendation for each row.
        It changes only Tech Debt&apos;s own figures: the consolidation plan,
        the deliverable, and the savings shown on the client&apos;s dashboards.
      </p>
      <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
        {DISPOSITIONS.map((d) => (
          <div key={d.label} className="contents">
            <dt className="font-semibold text-ink-primary">{d.label}</dt>
            <dd className="text-ink-secondary">{d.effect}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-ink-secondary">
        A disposition does not change ATT&amp;CK coverage, and nothing in CSF,
        Zero Trust or the Risk Register reads it. A tool marked Cut still counts
        toward ATT&amp;CK coverage.
      </p>
    </details>
  );
}
