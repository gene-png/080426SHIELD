"use client";
import * as React from "react";

import type { JSX } from "react";

interface DependencyStatus {
  status: string;
  required: boolean;
  detail: string;
}

interface ReadyResponse {
  status: string;
  ready: boolean;
  version: string;
  offenders: string[];
  checks: Record<string, DependencyStatus>;
}

// Pure fetch, no setState — so calling it inside the effect never trips
// react-hooks/set-state-in-effect. Callers apply the result in their own
// (deferred) promise callbacks, matching the AiStatusBanner idiom.
async function probeReady(): Promise<ReadyResponse> {
  const r = await fetch("/api/proxy/health/ready", { cache: "no-store" });
  if (!r.ok) throw new Error(`readiness probe failed (HTTP ${r.status})`);
  return (await r.json()) as ReadyResponse;
}

function readyError(e: unknown): string {
  return e instanceof Error ? e.message : "Readiness probe failed.";
}

/**
 * Operator view of the `/ready` dependency matrix (Sprint 6 T3): one row per
 * downstream dependency (db, redis, minio, keycloak, LLM) with a status dot, so
 * a demo operator can see "all green" at a glance and, when something is down,
 * exactly which dependency is the offender. Refreshes on mount.
 */
export function HealthMatrix(): JSX.Element {
  const [data, setData] = React.useState<ReadyResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    probeReady()
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(readyError(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-status-danger-border bg-status-danger-bg px-4 py-3 text-sm text-status-danger-fg"
      >
        {error}
      </div>
    );
  }

  if (!data) {
    return <p className="text-sm text-ink-tertiary">Checking dependencies…</p>;
  }

  return (
    <div className="space-y-4">
      <div
        role="status"
        className={
          "flex items-center gap-3 rounded-md border px-4 py-3 text-sm font-semibold " +
          (data.ready
            ? "border-status-success-border bg-status-success-bg text-status-success-fg"
            : "border-status-danger-border bg-status-danger-bg text-status-danger-fg")
        }
      >
        <span
          aria-hidden
          className={
            "inline-block h-2.5 w-2.5 rounded-full " +
            (data.ready ? "bg-status-success-fg" : "bg-status-danger-fg")
          }
        />
        {data.ready ? (
          <span>All systems ready</span>
        ) : (
          <span>
            Degraded — offender{data.offenders.length > 1 ? "s" : ""}:{" "}
            {data.offenders.join(", ")}
          </span>
        )}
        <span className="ml-auto font-normal text-ink-tertiary">
          v{data.version}
        </span>
      </div>

      <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle bg-surface-card">
        {Object.entries(data.checks).map(([name, check]) => (
          <li key={name} className="flex items-center gap-3 px-4 py-3 text-sm">
            <span
              aria-hidden
              className={
                "inline-block h-2.5 w-2.5 shrink-0 rounded-full " +
                (check.status === "ok"
                  ? "bg-status-success-fg"
                  : check.status === "dormant"
                    ? "bg-ink-tertiary"
                    : "bg-status-danger-fg")
              }
            />
            <span className="w-24 font-medium text-ink-primary">{name}</span>
            <span
              className={
                "w-20 text-xs font-semibold uppercase tracking-wide " +
                (check.status === "ok"
                  ? "text-status-success-fg"
                  : check.status === "dormant"
                    ? "text-ink-tertiary"
                    : "text-status-danger-fg")
              }
            >
              {check.status}
            </span>
            <span className="min-w-0 flex-1 truncate text-ink-secondary">
              {check.detail}
            </span>
            {!check.required ? (
              <span className="shrink-0 text-xs text-ink-tertiary">
                informational
              </span>
            ) : null}
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => {
          probeReady()
            .then((d) => {
              setData(d);
              setError(null);
            })
            .catch((e: unknown) => setError(readyError(e)));
        }}
        className="rounded-md border border-border bg-surface-card px-3 py-1.5 text-sm font-medium text-ink-primary hover:bg-surface-sunken"
      >
        Refresh
      </button>
    </div>
  );
}
