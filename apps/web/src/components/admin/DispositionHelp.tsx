import { DISPOSITION_LABEL } from "@/lib/tech_debt/dispositionLabels";

import type { JSX } from "react";

// #642. Every statement here was checked against the API's readers of
// `CapabilityItem.disposition` (the answer is on the issue). Tech Debt's own
// surfaces read it, and since #804 both cuts move the savings number
// (`tech_debt/savings.py::SAVINGS_DISPOSITIONS`). ATT&CK reads it too (#686,
// #801): `attack/retirement.py` labels a cut tool a planned retirement, and
// `attack/computed.py` (through `attack/after.py`) leaves it out of the coverage
// after planned changes. If a disposition starts feeding another service, this
// copy is wrong.
const DISPOSITIONS: ReadonlyArray<{ label: string; effect: string }> = [
  {
    label: "Undecided",
    effect:
      "No recommendation yet. Counted under Undecided in the consolidation plan.",
  },
  {
    label: DISPOSITION_LABEL.keep,
    effect:
      "Recommend keeping the tool. Counted under Keep; no figure changes.",
  },
  {
    label: DISPOSITION_LABEL.consolidate,
    effect:
      "Recommend retiring the tool because another tool covers what it does. Its full annual cost is added to the estimated annual savings, as for Cut.",
  },
  {
    label: DISPOSITION_LABEL.cut,
    effect:
      "Recommend retiring the tool. Its annual cost is added to the estimated annual savings. If a row marked to cut has no cost, the savings figure is shown as a lower bound.",
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
        It changes Tech Debt&apos;s own figures (the consolidation plan, the
        deliverable, and the savings shown on the client&apos;s dashboards) and,
        for Cut and Cut, covered by another tool, the ATT&amp;CK coverage after
        planned changes.
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
        Nothing in CSF, Zero Trust or the Risk Register reads it. In ATT&amp;CK
        a tool marked Cut, or Cut, covered by another tool, is labelled a
        planned retirement: it still counts toward today&apos;s coverage, and
        not toward the coverage after planned changes.
      </p>
    </details>
  );
}
