import type { JSX } from "react";

/**
 * The section header of Gene's UI page plan v2, rules 2 and 6 (#736,
 * issuecomment-6116093149): the title; "What this section is for", in one
 * plain sentence; "What you can do here", in one to three short bullets; and
 * its visibility state. v2 supersedes v1's "What this page is for".
 *
 * The two labels and the three visibility labels are Gene's, verbatim. The
 * sentence and bullets are the caller's, and go to Gene verbatim per section.
 * A term/definition list adds no punctuation of its own, so no unapproved
 * character ships between a label and its text.
 */
export type Visibility = "internal" | "client-preview" | "released";

export const VISIBILITY_LABEL: Record<Visibility, string> = {
  internal: "Internal only",
  "client-preview": "Client preview",
  released: "Released to client",
};

const VISIBILITY_CLASS: Record<Visibility, string> = {
  internal:
    "border-status-warning-border bg-status-warning-bg text-status-warning-fg",
  "client-preview":
    "border-status-info-fg bg-status-info-bg text-status-info-fg",
  released:
    "border-status-success-border bg-status-success-bg text-status-success-fg",
};

export function SectionHeader({
  title,
  purpose,
  canDo,
  visibility,
}: {
  title: string;
  purpose: string;
  /** One to three short bullets (plan v2, rule 2). */
  canDo: readonly string[];
  visibility: Visibility;
}): JSX.Element {
  if (canDo.length < 1 || canDo.length > 3) {
    throw new Error(
      `SectionHeader "${title}": "What you can do here" takes one to three bullets (plan v2, rule 2), got ${canDo.length}.`,
    );
  }
  return (
    <header className="flex flex-col gap-3 px-6 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-primary">
          {title}
        </h1>
        <span
          data-testid="section-visibility"
          className={
            "rounded-full border px-2.5 py-0.5 text-xs font-semibold " +
            VISIBILITY_CLASS[visibility]
          }
        >
          {VISIBILITY_LABEL[visibility]}
        </span>
      </div>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
        <dt className="font-semibold text-ink-primary">
          What this section is for
        </dt>
        <dd className="text-ink-secondary">{purpose}</dd>
        <dt className="font-semibold text-ink-primary">What you can do here</dt>
        <dd className="text-ink-secondary">
          <ul className="list-disc pl-5">
            {canDo.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </dd>
      </dl>
    </header>
  );
}
