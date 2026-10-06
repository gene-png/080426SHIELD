import type { JSX } from "react";

import { aiSourceIsWarning, type AiSource } from "@/lib/aiSource/types";

/**
 * #646: the API's own sentence saying which mode drafted an assessment's AI
 * suggestions, in every state -- live included, so "no warning" is never read
 * as "nobody looked". Warning-toned for offline test data, mixed and not
 * recorded. Rendered by the admin workspaces and the client dashboards alike.
 */
export function AiSourceNote({
  source,
  className,
}: {
  source: AiSource;
  className?: string;
}): JSX.Element {
  const warning = aiSourceIsWarning(source);
  return (
    <p
      className={[
        "text-sm",
        warning ? "font-semibold text-status-warning-fg" : "text-ink-secondary",
        className ?? "",
      ]
        .join(" ")
        .trim()}
      role={warning ? "alert" : undefined}
      data-testid="ai-source"
      data-state={source.state}
    >
      {source.sentence}
    </p>
  );
}
