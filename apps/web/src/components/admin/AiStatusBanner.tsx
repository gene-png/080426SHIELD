"use client";
import * as React from "react";

import type { JSX } from "react";

interface AiStatus {
  mode: string;
  provider: string;
  model: string;
  ready: boolean;
  detail: string;
}

/**
 * Warns the consultant when AI features won't run a live call (fixture mode,
 * or live mode missing its key) - so a failed/empty extraction is explained
 * up front rather than surfacing as an opaque 500. Renders nothing when AI is
 * ready or while the status is still loading.
 */
export function AiStatusBanner(): JSX.Element | null {
  const [status, setStatus] = React.useState<AiStatus | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    fetch("/api/proxy/admin/ai-status", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: AiStatus | null) => {
        if (!cancelled) setStatus(d);
      })
      .catch(() => {
        /* non-blocking */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!status || status.ready) return null;

  return (
    <div
      role="status"
      className="rounded-md border border-status-warning-border bg-status-warning-bg px-4 py-3 text-sm text-status-warning-fg"
    >
      <span className="font-semibold">AI is not live.</span> {status.detail}{" "}
      Extraction and other AI steps won&apos;t produce results until this is
      configured.
    </div>
  );
}
